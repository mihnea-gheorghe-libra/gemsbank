from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from backend.accounts.service import AccountsService, get_accounts_service
from backend.config import settings
from backend.helpers.context import Actor
from backend.ledger.service import LedgerService, get_ledger_service
from backend.payments.adapters import PolicyOutcome, StaticLimitPolicy
from backend.payments.service import PaymentsService, get_payments_service
from backend.payments.validation import normalise_counterparty, normalise_reference

_MAX_PROPOSAL_MINOR = 10**12

_CURRENCY_WORDS = {
    "ron": "RON",
    "lei": "RON",
    "leu": "RON",
    "lej": "RON",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "dolar": "USD",
    "dolari": "USD",
}

_KIND_WORDS = {
    "current": "current",
    "curent": "current",
    "checking": "current",
    "everyday": "current",
    "savings": "savings",
    "saving": "savings",
    "economii": "savings",
    "invest": "invest",
    "investment": "invest",
    "investments": "invest",
    "investitii": "invest",
}


def format_minor(amount_minor: int, currency: str) -> str:
    sign = "-" if amount_minor < 0 else ""
    units, subunits = divmod(abs(amount_minor), 100)
    grouped = f"{units:,}".replace(",", ".")
    return f"{sign}{grouped},{subunits:02d} {currency}"


class AccountBalance(BaseModel):
    account_id: str = Field(alias="accountId")
    label: str
    kind: str
    currency: str
    iban_masked: str = Field(alias="ibanMasked")
    status: str
    balance_minor: int = Field(alias="balanceMinorUnits")
    balance_formatted: str = Field(alias="balanceFormatted")
    model_config = {"populate_by_name": True}


class CurrencyTotal(BaseModel):
    currency: str
    total_minor: int = Field(alias="totalMinorUnits")
    total_formatted: str = Field(alias="totalFormatted")
    account_count: int = Field(alias="accountCount")
    model_config = {"populate_by_name": True}


class BalancesInput(BaseModel):
    account_ref: str | None = Field(
        default=None,
        alias="accountRef",
        max_length=64,
        description=(
            "Optional. The account the user named, in their own words: a label such as "
            "'savings' or 'current', a currency such as 'EUR', or the last digits of an "
            "IBAN. Leave empty to report on every account."
        ),
    )
    model_config = {"populate_by_name": True}


class BalancesOutput(BaseModel):
    status: Literal["ok", "no_accounts", "ambiguous", "no_match"]
    matched_ref: str | None = Field(default=None, alias="matchedRef")
    accounts: list[AccountBalance] = Field(default_factory=list)
    totals: list[CurrencyTotal] = Field(default_factory=list)
    candidates: list[AccountBalance] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


class BeneficiariesInput(BaseModel):
    pass


class BeneficiaryView(BaseModel):
    name: str
    iban: str
    iban_masked: str = Field(alias="ibanMasked")
    model_config = {"populate_by_name": True}


class BeneficiariesOutput(BaseModel):
    beneficiaries: list[BeneficiaryView] = Field(default_factory=list)


class TransferProposalInput(BaseModel):
    source_account_ref: str = Field(
        alias="sourceAccountRef",
        max_length=64,
        description=(
            "The account the money should leave, in the user's own words: a label such as "
            "'current', a currency such as 'RON', or the last digits of an IBAN."
        ),
    )
    target_account_ref: str | None = Field(
        default=None,
        alias="targetAccountRef",
        max_length=64,
        description="For a transfer between the user's own accounts: which one receives it.",
    )
    target_iban: str | None = Field(
        default=None,
        alias="targetIban",
        max_length=34,
        description=(
            "For a transfer to someone else: the full IBAN. Only ever an IBAN the user "
            "gave you, or one returned by payments.beneficiaries.list. Never invent one."
        ),
    )
    counterparty: str | None = Field(
        default=None,
        max_length=70,
        description="The name of the person or company being paid. Required with targetIban.",
    )
    amount_minor: int = Field(
        alias="amountMinorUnits",
        ge=1,
        le=_MAX_PROPOSAL_MINOR,
        description="The amount in integer minor units: 12,50 RON is 1250.",
    )
    reference: str = Field(
        max_length=140, description="What the payment is for, as the user described it."
    )
    model_config = {"populate_by_name": True}


class ProposalBlocker(BaseModel):
    code: str
    message: str


class TransferProposalOutput(BaseModel):
    status: Literal["proposed", "blocked", "needs_clarification"]
    proposal_id: str | None = Field(default=None, alias="proposalId")
    source_account_id: str | None = Field(default=None, alias="sourceAccountId")
    source_label: str | None = Field(default=None, alias="sourceLabel")
    source_iban_masked: str | None = Field(default=None, alias="sourceIbanMasked")
    target_account_id: str | None = Field(default=None, alias="targetAccountId")
    target_iban: str | None = Field(default=None, alias="targetIban")
    target_iban_masked: str | None = Field(default=None, alias="targetIbanMasked")
    counterparty: str | None = None
    amount_minor: int | None = Field(default=None, alias="amountMinorUnits")
    amount_formatted: str | None = Field(default=None, alias="amountFormatted")
    currency: str | None = None
    reference: str | None = None
    balance_after_minor: int | None = Field(default=None, alias="balanceAfterMinorUnits")
    balance_after_formatted: str | None = Field(
        default=None, alias="balanceAfterFormatted"
    )
    requires_signature: bool = Field(default=False, alias="requiresSignature")
    requires_human_confirmation: bool = Field(default=True, alias="requiresHumanConfirmation")
    auto_approval_eligible: bool = Field(default=False, alias="autoApprovalEligible")
    auto_approval_reason: str = Field(
        default="no_mandate", alias="autoApprovalReason"
    )
    candidates: list[AccountBalance] = Field(default_factory=list)
    blockers: list[ProposalBlocker] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


def _match_score(account: dict, ref: str) -> int:
    needle = ref.strip().lower()
    if not needle:
        return 0
    if needle == account["accountId"].lower():
        return 100
    iban = account["iban"].lower()
    if needle.replace(" ", "") == iban:
        return 100
    digits = "".join(char for char in needle if char.isdigit())
    if len(digits) >= 4 and iban.endswith(digits):
        return 90
    currency = account["currency"].upper()
    kind = account["kind"].lower()
    label = account["label"].lower()

    score = 0
    if needle == label:
        score = max(score, 80)
    elif needle in label or label in needle:
        score = max(score, 50)

    words = [word for word in "".join(
        char if char.isalnum() else " " for char in needle
    ).split() if word]

    named_currency = {_CURRENCY_WORDS[word] for word in words if word in _CURRENCY_WORDS}
    named_kind = {_KIND_WORDS[word] for word in words if word in _KIND_WORDS}

    if named_currency and named_kind:
        if currency in named_currency and kind in named_kind:
            return 85
        return 0
    if named_kind:
        score = max(score, 70) if kind in named_kind else score
    if named_currency:
        score = max(score, 60) if currency in named_currency else score

    for word in words:
        if len(word) >= 3 and word in label:
            score = max(score, 40)
    return score


def _to_balance(account: dict) -> AccountBalance:
    minor = account["balance"]["minorUnits"]
    return AccountBalance(
        accountId=account["accountId"],
        label=account["label"],
        kind=account["kind"],
        currency=account["currency"],
        ibanMasked=account["ibanMasked"],
        status=account["status"],
        balanceMinorUnits=minor,
        balanceFormatted=format_minor(minor, account["currency"]),
    )


def _resolve_ref(accounts: list[dict], ref: str) -> tuple[list[dict], int]:
    scored = [(account, _match_score(account, ref)) for account in accounts]
    best = max((score for _, score in scored), default=0)
    if best == 0:
        return [], 0
    return [account for account, score in scored if score == best], best


def _totals(accounts: list[dict]) -> list[CurrencyTotal]:
    grouped: dict[str, list[dict]] = {}
    for account in accounts:
        grouped.setdefault(account["currency"], []).append(account)
    totals = []
    for currency, rows in sorted(grouped.items()):
        minor = sum(row["balance"]["minorUnits"] for row in rows)
        totals.append(
            CurrencyTotal(
                currency=currency,
                totalMinorUnits=minor,
                totalFormatted=format_minor(minor, currency),
                accountCount=len(rows),
            )
        )
    return totals


async def _accounts_for(actor: Actor, service: AccountsService) -> list[dict]:
    return await service.list_for_user(actor.subject_id())


async def resolve_balances(
    actor: Actor,
    payload: BaseModel,
    accounts_service: AccountsService | None = None,
) -> BaseModel:
    assert isinstance(payload, BalancesInput)
    service = accounts_service or get_accounts_service()
    accounts = await _accounts_for(actor, service)
    if not accounts:
        return BalancesOutput(status="no_accounts")

    totals = _totals(accounts)
    if not payload.account_ref:
        return BalancesOutput(
            status="ok",
            accounts=[_to_balance(account) for account in accounts],
            totals=totals,
        )

    matches, _ = _resolve_ref(accounts, payload.account_ref)
    if not matches:
        return BalancesOutput(
            status="no_match",
            matchedRef=payload.account_ref,
            candidates=[_to_balance(account) for account in accounts],
            totals=totals,
        )
    if len(matches) > 1:
        return BalancesOutput(
            status="ambiguous",
            matchedRef=payload.account_ref,
            candidates=[_to_balance(account) for account in matches],
            totals=totals,
        )
    return BalancesOutput(
        status="ok",
        matchedRef=payload.account_ref,
        accounts=[_to_balance(matches[0])],
        totals=totals,
    )


async def resolve_beneficiaries(
    actor: Actor,
    payload: BaseModel,
    payments_service: PaymentsService | None = None,
) -> BaseModel:
    assert isinstance(payload, BeneficiariesInput)
    service = payments_service or get_payments_service()
    data = await service.list_beneficiaries(actor.subject_id())
    return BeneficiariesOutput(
        beneficiaries=[
            BeneficiaryView(
                name=row["name"],
                iban=row["iban"],
                ibanMasked=row.get("ibanMasked") or f"•• {row['iban'][-4:]}",
            )
            for row in data["beneficiaries"]
        ]
    )


async def _spent_today(accounts: list[dict], ledger: LedgerService) -> int:
    account_ids = [account["accountId"] for account in accounts]
    midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return await ledger.debited_since(account_ids, midnight)


async def resolve_transfer_proposal(
    actor: Actor,
    payload: BaseModel,
    accounts_service: AccountsService | None = None,
    ledger_service: LedgerService | None = None,
) -> BaseModel:
    assert isinstance(payload, TransferProposalInput)
    accounts_svc = accounts_service or get_accounts_service()
    ledger = ledger_service or get_ledger_service()

    accounts = await _accounts_for(actor, accounts_svc)
    if not accounts:
        return TransferProposalOutput(
            status="blocked",
            blockers=[ProposalBlocker(code="no_accounts", message="This customer holds no accounts.")],
        )

    source_matches, _ = _resolve_ref(accounts, payload.source_account_ref)
    if not source_matches:
        return TransferProposalOutput(
            status="needs_clarification",
            candidates=[_to_balance(account) for account in accounts],
            blockers=[
                ProposalBlocker(
                    code="source_not_found",
                    message="No account of theirs matches that description.",
                )
            ],
        )
    if len(source_matches) > 1:
        return TransferProposalOutput(
            status="needs_clarification",
            candidates=[_to_balance(account) for account in source_matches],
            blockers=[
                ProposalBlocker(
                    code="source_ambiguous",
                    message="More than one of their accounts matches that description.",
                )
            ],
        )
    source = source_matches[0]

    blockers: list[ProposalBlocker] = []
    target: dict | None = None
    target_iban: str | None = None
    counterparty: str

    if payload.target_account_ref:
        others = [row for row in accounts if row["accountId"] != source["accountId"]]
        target_matches, _ = _resolve_ref(others, payload.target_account_ref)
        if not target_matches:
            return TransferProposalOutput(
                status="needs_clarification",
                candidates=[_to_balance(account) for account in others],
                blockers=[
                    ProposalBlocker(
                        code="target_not_found",
                        message="No other account of theirs matches that description.",
                    )
                ],
            )
        if len(target_matches) > 1:
            return TransferProposalOutput(
                status="needs_clarification",
                candidates=[_to_balance(account) for account in target_matches],
                blockers=[
                    ProposalBlocker(
                        code="target_ambiguous",
                        message="More than one of their accounts matches that description.",
                    )
                ],
            )
        target = target_matches[0]
        target_iban = target["iban"]
        counterparty = normalise_counterparty(
            payload.counterparty or target.get("holderName") or target["label"]
        )
    elif payload.target_iban:
        resolved = await accounts_svc.resolve_iban(payload.target_iban)
        if resolved is None:
            return TransferProposalOutput(
                status="blocked",
                blockers=[
                    ProposalBlocker(
                        code="iban_unreachable",
                        message=(
                            "GEMS can only reach accounts held at GEMS. That IBAN is not one "
                            "of them, and external rails are not connected in this demo."
                        ),
                    )
                ],
            )
        if not payload.counterparty:
            return TransferProposalOutput(
                status="needs_clarification",
                blockers=[
                    ProposalBlocker(
                        code="counterparty_missing",
                        message="A payment to an IBAN needs the payee's name.",
                    )
                ],
            )
        target_iban = resolved.iban
        target = {
            "accountId": resolved.id,
            "iban": resolved.iban,
            "ibanMasked": resolved.masked_iban(),
            "currency": resolved.currency,
            "kind": resolved.kind.value,
            "label": resolved.label,
            "status": resolved.status.value,
            "holderName": resolved.holder_name,
        }
        counterparty = normalise_counterparty(payload.counterparty)
    else:
        return TransferProposalOutput(
            status="needs_clarification",
            blockers=[
                ProposalBlocker(
                    code="target_missing",
                    message="Say where the money should go: one of their accounts, or an IBAN.",
                )
            ],
        )

    if target["accountId"] == source["accountId"]:
        blockers.append(
            ProposalBlocker(code="self_transfer", message="An account cannot pay itself.")
        )
    if source["status"] != "active":
        blockers.append(
            ProposalBlocker(
                code="source_not_active",
                message=f"That account is {source['status']} and cannot send money.",
            )
        )
    if target["status"] == "closed":
        blockers.append(
            ProposalBlocker(
                code="target_closed", message="The receiving account is closed."
            )
        )
    if source["currency"] != target["currency"]:
        blockers.append(
            ProposalBlocker(
                code="currency_mismatch",
                message=(
                    f"GEMS does not convert currencies in a payment. "
                    f"{source['currency']} cannot be sent to a {target['currency']} account."
                ),
            )
        )

    balance = source["balance"]["minorUnits"]
    if payload.amount_minor > balance:
        blockers.append(
            ProposalBlocker(
                code="insufficient_funds",
                message="That is more than the account holds.",
            )
        )

    policy = StaticLimitPolicy(settings)
    spent = await _spent_today(accounts, ledger)
    decision = policy.evaluate(payload.amount_minor, source["currency"], spent)
    if decision.outcome is PolicyOutcome.DENY:
        blockers.append(
            ProposalBlocker(
                code=decision.reason,
                message=(
                    "That is above the single-payment limit."
                    if decision.reason == "over_per_transaction_limit"
                    else "That would take them past today's payment limit."
                ),
            )
        )

    if blockers:
        return TransferProposalOutput(
            status="blocked",
            sourceAccountId=source["accountId"],
            sourceLabel=source["label"],
            sourceIbanMasked=source["ibanMasked"],
            amountMinorUnits=payload.amount_minor,
            amountFormatted=format_minor(payload.amount_minor, source["currency"]),
            currency=source["currency"],
            blockers=blockers,
        )

    return TransferProposalOutput(
        status="proposed",
        proposalId=f"prop-{source['accountId'][:8]}-{payload.amount_minor}",
        sourceAccountId=source["accountId"],
        sourceLabel=source["label"],
        sourceIbanMasked=source["ibanMasked"],
        targetAccountId=target["accountId"] if payload.target_account_ref else None,
        targetIban=target_iban,
        targetIbanMasked=target["ibanMasked"],
        counterparty=counterparty,
        amountMinorUnits=payload.amount_minor,
        amountFormatted=format_minor(payload.amount_minor, source["currency"]),
        currency=source["currency"],
        reference=normalise_reference(payload.reference),
        balanceAfterMinorUnits=balance - payload.amount_minor,
        balanceAfterFormatted=format_minor(
            balance - payload.amount_minor, source["currency"]
        ),
        requiresSignature=decision.outcome is PolicyOutcome.REQUIRE_APPROVAL,
        requiresHumanConfirmation=True,
        autoApprovalEligible=False,
        autoApprovalReason="no_mandate",
    )
