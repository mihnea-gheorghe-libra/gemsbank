import secrets
from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SyntheticCardNumberGenerator:
    """Demo only. Never produces or stores a full PAN — see PROMPT.md §0
    (no real card data, nothing here is in PCI scope)."""

    def last4(self) -> str:
        return f"{secrets.randbelow(10_000):04d}"


class RandomCardPinGenerator:
    def generate(self) -> str:
        return f"{secrets.randbelow(10_000):04d}"


class RandomCvvGenerator:
    def generate(self) -> str:
        return f"{secrets.randbelow(1_000):03d}"
