from datetime import datetime, timezone

from backend.accounts.account import AccountKind

STARTER_ACCOUNTS: tuple[tuple[str, AccountKind, str], ...] = (
    ("RON", AccountKind.CURRENT, "Cont curent"),
    ("RON", AccountKind.SAVINGS, "Economii"),
    ("EUR", AccountKind.SAVINGS, "Economii EUR"),
    ("USD", AccountKind.SAVINGS, "Economii USD"),
)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)
