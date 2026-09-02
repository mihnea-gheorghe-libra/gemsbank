import pytest

from backend.admin.service import ApproveCreditApplication, RejectCreditApplication
from backend.credits.service import SubmitCreditApplication, WithdrawCreditApplication
from backend.helpers.errors import (
    AuthorizationError,
    IllegalTransitionError,
    NotFoundError,
    ValidationError,
)
from backend.tests.admin_fakes import (
    FakeCustomer,
    account,
    admin_context,
    build_admin_service,
    customer_context,
)


async def _submit(parts, payout) -> str:
    result = await parts["credits"]._handle_submit(
        SubmitCreditApplication(
            product_id="personal",
            amount_minor=5_000_000,
            term_months=24,
            purpose="Renovation",
            payout_account_id=payout.id,
        ),
        customer_context(),
        session=None,
    )
    return result.data["applicationId"]


def _service():
    payout = account()
    service, parts = build_admin_service(
        accounts=[payout], customers=[FakeCustomer("user-1", "anapop")]
    )
    return service, parts, payout


async def test_a_new_application_starts_pending_review() -> None:
    _, parts, payout = _service()

    application_id = await _submit(parts, payout)

    assert parts["applications"].applications[application_id].status == "review"


async def test_approving_records_the_reason_and_the_decider() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)

    result = await service._handle_approve(
        ApproveCreditApplication(
            application_id=application_id, reason="Income verified against payslips"
        ),
        admin_context(),
        session=None,
    )

    stored = parts["applications"].applications[application_id]
    assert stored.status == "approved"
    assert stored.decision_reason == "Income verified against payslips"
    assert stored.decided_by == "admin:admin"
    assert result.data["status"] == "approved"
    assert result.data["decidedAt"] is not None


async def test_rejecting_records_the_reason() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)

    await service._handle_reject(
        RejectCreditApplication(
            application_id=application_id, reason="Existing exposure is too high"
        ),
        admin_context(),
        session=None,
    )

    stored = parts["applications"].applications[application_id]
    assert stored.status == "rejected"
    assert stored.decision_reason == "Existing exposure is too high"


async def test_a_decided_application_cannot_be_decided_again() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)
    await service._handle_approve(
        ApproveCreditApplication(
            application_id=application_id, reason="Income verified against payslips"
        ),
        admin_context(),
        session=None,
    )

    with pytest.raises(IllegalTransitionError):
        await service._handle_approve(
            ApproveCreditApplication(
                application_id=application_id, reason="Income verified against payslips"
            ),
            admin_context(),
            session=None,
        )
    with pytest.raises(IllegalTransitionError):
        await service._handle_reject(
            RejectCreditApplication(
                application_id=application_id, reason="Changed my mind about this"
            ),
            admin_context(),
            session=None,
        )


async def test_a_decided_application_can_no_longer_be_withdrawn_by_the_customer() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)
    await service._handle_reject(
        RejectCreditApplication(
            application_id=application_id, reason="Existing exposure is too high"
        ),
        admin_context(),
        session=None,
    )

    with pytest.raises(IllegalTransitionError):
        await parts["credits"]._handle_withdraw(
            WithdrawCreditApplication(application_id=application_id),
            customer_context(),
            session=None,
        )


async def test_a_decision_needs_a_reason() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)

    with pytest.raises(ValidationError):
        await service._handle_approve(
            ApproveCreditApplication(application_id=application_id, reason=" "),
            admin_context(),
            session=None,
        )
    assert parts["applications"].applications[application_id].status == "review"


async def test_a_customer_actor_cannot_decide_an_application() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)

    with pytest.raises(AuthorizationError):
        await service._handle_approve(
            ApproveCreditApplication(
                application_id=application_id, reason="Approving my own loan"
            ),
            customer_context(),
            session=None,
        )


async def test_deciding_an_unknown_application_is_a_not_found() -> None:
    service, _, _ = _service()

    with pytest.raises(NotFoundError):
        await service._handle_approve(
            ApproveCreditApplication(application_id="nope", reason="Nothing to decide"),
            admin_context(),
            session=None,
        )


async def test_the_review_queue_lists_pending_applications_with_the_applicant() -> None:
    service, parts, payout = _service()
    application_id = await _submit(parts, payout)

    queue = await service.list_applications("review", None, None)

    assert queue["total"] == 1
    assert queue["applications"][0]["applicationId"] == application_id
    assert queue["applications"][0]["applicant"]["username"] == "anapop"


async def test_the_review_queue_shows_supporting_data_for_a_pending_application() -> None:
    payout = account()
    other_account = account(iban="RO00TESTBANK0000000099")
    service, parts = build_admin_service(
        accounts=[payout, other_account], customers=[FakeCustomer("user-1", "anapop")]
    )
    await parts["ledger"].transfer(
        source_account_id="house:settlement:RON",
        target_account_id=payout.id,
        amount_minor=800_000,
        currency="RON",
        reference="Salariu",
        counterparty="Employer SRL",
        category="income",
        correlation_id="corr-income",
        actor="system:seed",
    )
    application_id = await _submit(parts, payout)

    queue = await service.list_applications("review", None, None)
    support = queue["applications"][0]["support"]

    from backend.products.catalogue import estimate_repayment

    monthly, _, _ = estimate_repayment(5_000_000, 24, 830)
    assert support["monthlyIncomeMinorUnits"] == round(800_000 / 3)
    assert support["estimatedMonthlyPaymentMinorUnits"] == monthly
    assert support["currentBalanceMinorUnits"] == 800_000
    assert support["currentBalanceCurrency"] == "RON"
    assert support["otherActiveCredits"] == []


async def test_a_stored_monthly_income_is_used_instead_of_estimated() -> None:
    payout = account()
    customer = FakeCustomer("user-1", "anapop", monthly_income_minor=1_200_000)
    service, parts = build_admin_service(accounts=[payout], customers=[customer])
    await _submit(parts, payout)

    queue = await service.list_applications("review", None, None)

    assert queue["applications"][0]["support"]["monthlyIncomeMinorUnits"] == 1_200_000
    assert customer.monthly_income_minor == 1_200_000


async def test_a_decided_application_carries_no_support_block() -> None:
    payout = account()
    service, parts = build_admin_service(
        accounts=[payout], customers=[FakeCustomer("user-1", "anapop")]
    )
    application_id = await _submit(parts, payout)
    await service._handle_approve(
        ApproveCreditApplication(application_id=application_id, reason="Income verified"),
        admin_context(),
        session=None,
    )

    queue = await service.list_applications(None, None, None)

    assert "support" not in queue["applications"][0]


async def test_an_open_ended_line_has_no_estimated_monthly_payment() -> None:
    payout = account()
    service, parts = build_admin_service(
        accounts=[payout], customers=[FakeCustomer("user-1", "anapop")]
    )
    result = await parts["credits"]._handle_submit(
        SubmitCreditApplication(
            product_id="line",
            amount_minor=100_000,
            term_months=None,
            purpose="",
            payout_account_id=payout.id,
        ),
        customer_context(),
        session=None,
    )

    queue = await service.list_applications("review", None, None)

    assert result.data["applicationId"] == queue["applications"][0]["applicationId"]
    assert queue["applications"][0]["support"]["estimatedMonthlyPaymentMinorUnits"] is None


async def test_other_active_credits_lists_the_customers_approved_applications() -> None:
    payout = account()
    service, parts = build_admin_service(
        accounts=[payout], customers=[FakeCustomer("user-1", "anapop")]
    )
    first_id = await _submit(parts, payout)
    await service._handle_approve(
        ApproveCreditApplication(application_id=first_id, reason="Income verified"),
        admin_context(),
        session=None,
    )
    second_id = await _submit(parts, payout)

    queue = await service.list_applications("review", None, None)
    others = queue["applications"][0]["support"]["otherActiveCredits"]

    assert queue["applications"][0]["applicationId"] == second_id
    assert [o["applicationId"] for o in others] == [first_id]


async def test_user_detail_carries_support_only_for_pending_applications() -> None:
    payout = account()
    service, parts = build_admin_service(
        accounts=[payout], customers=[FakeCustomer("user-1", "anapop")]
    )
    first_id = await _submit(parts, payout)
    await service._handle_approve(
        ApproveCreditApplication(application_id=first_id, reason="Income verified"),
        admin_context(),
        session=None,
    )
    await _submit(parts, payout)

    detail = await service.customer_detail("user-1")
    by_status = {a["status"]: a for a in detail["creditApplications"]}

    assert "support" in by_status["review"]
    assert "support" not in by_status["approved"]
