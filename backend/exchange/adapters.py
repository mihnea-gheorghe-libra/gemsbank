from datetime import date, datetime, timezone
from typing import Any

import httpx

from backend.exchange.validation import to_rate_micro
from backend.helpers.errors import DeliveryError


class FrankfurterRateClient:
    def __init__(self, base_url: str, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch(self, base: str, quote: str) -> tuple[int, date]:
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout), follow_redirects=True
            ) as client:
                response = await client.get(
                    f"{self._base_url}/latest", params={"base": base, "symbols": quote}
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DeliveryError(
                "The exchange rate provider did not answer.",
                details={"base": base, "quote": quote},
            ) from exc

        rates = payload.get("rates")
        if not isinstance(rates, dict) or quote not in rates:
            raise DeliveryError(
                "The exchange rate provider returned no rate for that pair.",
                details={"base": base, "quote": quote},
            )
        stamp = payload.get("date")
        as_of = date.fromisoformat(str(stamp)) if stamp else datetime.now(timezone.utc).date()
        return to_rate_micro(rates[quote], field="rate"), as_of
