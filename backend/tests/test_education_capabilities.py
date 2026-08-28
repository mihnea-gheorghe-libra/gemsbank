import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.capabilities import education as caps
from backend.capabilities.education_docs import search_education_docs

USER_ID = "user-1"


class _FakeActor:
    def subject_id(self) -> str:
        return USER_ID


ACTOR = _FakeActor()


def account(
    account_id: str,
    label: str,
    kind: str,
    currency: str,
    minor: int,
    iban: str,
    status: str = "active",
) -> dict:
    return {
        "accountId": account_id,
        "iban": iban,
        "ibanMasked": f"•• {iban[-4:]}",
        "holderName": "POPESCU ION",
        "currency": currency,
        "kind": kind,
        "label": label,
        "status": status,
        "balance": {"minorUnits": minor, "currency": currency},
    }


ACCOUNTS = [
    account("acc-ron-cur", "Current RON", "current", "RON", 250000, "RO49AAAA1B31007593840001"),
    account("acc-ron-sav", "Savings RON", "savings", "RON", 800000, "RO49AAAA1B31007593840002"),
    account("acc-invest", "Invest RON", "invest", "RON", 500000, "RO49AAAA1B31007593840003"),
]


class FakeAccounts:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    async def list_for_user(self, user_id: str) -> list[dict]:
        assert user_id == USER_ID
        return self._rows


class _FakeGoal:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeGoals:
    def __init__(self, existing: _FakeGoal | None = None) -> None:
        self._existing = existing
        self.add_calls: list[object] = []

    async def get_for_user(self, user_id: str):
        assert user_id == USER_ID
        return self._existing

    async def list_active_for_user(self, user_id: str):
        assert user_id == USER_ID
        return [self._existing] if self._existing else []

    async def add(self, *args, **kwargs):
        self.add_calls.append((args, kwargs))
        raise AssertionError("a proposal must never create the goal")


def _today() -> date:
    return datetime.now(timezone.utc).date()


FUTURE_DATE = _today() + timedelta(days=180)


def propose(
    accounts_rows: list[dict] | None = None,
    existing_goal: _FakeGoal | None = None,
    **kwargs,
):
    goals = FakeGoals(existing=existing_goal)
    payload = caps.GoalProposalInput(**kwargs)
    result = asyncio.run(
        caps.resolve_goal_proposal(
            ACTOR,
            payload,
            accounts_service=FakeAccounts(accounts_rows if accounts_rows is not None else ACCOUNTS),
            goals_service=goals,
        )
    )
    return result, goals


def test_search_returns_the_relevant_article_by_keyword() -> None:
    results = search_education_docs("fond de urgenta")
    assert any(doc.id == "emergency-fund" for doc in results)


def test_search_falls_back_to_the_full_list_for_an_unmatched_query() -> None:
    results = search_education_docs("zzzzz not a real word")
    assert len(results) > 0


def test_a_clean_proposal_never_creates_the_goal() -> None:
    result, goals = propose(
        accountRef="current",
        name="Vacation",
        targetMinorUnits=300000,
        targetDate=FUTURE_DATE,
    )
    assert result.status == "proposed"
    assert result.requires_human_confirmation is True
    assert result.account_id == "acc-ron-cur"
    assert result.target_formatted == "3.000,00 RON"
    assert goals.add_calls == []


def test_investment_accounts_are_not_eligible_to_fund_a_goal() -> None:
    result, _ = propose(
        accounts_rows=[ACCOUNTS[2]],
        accountRef="invest",
        name="Vacation",
        targetMinorUnits=100000,
        targetDate=FUTURE_DATE,
    )
    assert result.status == "blocked"
    assert "no_eligible_accounts" in {b.code for b in result.blockers}


def test_a_duplicate_goal_name_blocks_a_new_proposal() -> None:
    result, _ = propose(
        existing_goal=_FakeGoal("Vacation"),
        accountRef="current",
        name="Vacation",
        targetMinorUnits=100000,
        targetDate=FUTURE_DATE,
    )
    assert result.status == "blocked"
    assert "duplicate_goal_name" in {b.code for b in result.blockers}


def test_an_unmatched_account_ref_asks_instead_of_guessing() -> None:
    result, _ = propose(
        accountRef="my mortgage",
        name="Vacation",
        targetMinorUnits=100000,
        targetDate=FUTURE_DATE,
    )
    assert result.status == "needs_clarification"
    assert "account_not_found" in {b.code for b in result.blockers}


def test_an_ambiguous_account_ref_asks_instead_of_picking_one() -> None:
    result, _ = propose(
        accountRef="ron",
        name="Vacation",
        targetMinorUnits=100000,
        targetDate=FUTURE_DATE,
    )
    assert result.status == "needs_clarification"
    assert "account_ambiguous" in {b.code for b in result.blockers}


def test_a_past_target_date_is_blocked_not_silently_corrected() -> None:
    result, _ = propose(
        accountRef="current",
        name="Vacation",
        targetMinorUnits=100000,
        targetDate=_today() - timedelta(days=1),
    )
    assert result.status == "blocked"
    assert "invalid_targetDate" in {b.code for b in result.blockers}


def test_a_zero_or_negative_target_amount_never_reaches_the_resolver() -> None:
    for amount in (0, -1):
        with pytest.raises(PydanticValidationError):
            caps.GoalProposalInput(
                accountRef="current",
                name="Vacation",
                targetMinorUnits=amount,
                targetDate=FUTURE_DATE,
            )
