from datetime import datetime, timedelta
from typing import Any

STREAK_LOOKBACK_WEEKS = 52


def week_key(moment: datetime) -> str:
    year, week, _ = moment.isocalendar()
    return f"{year}-W{week:02d}"


def _weeks_before(moment: datetime, weeks: int) -> datetime:
    return moment - timedelta(weeks=weeks)


def contributed_weeks(movements: list[dict[str, Any]]) -> set[str]:
    weeks: set[str] = set()
    for movement in movements:
        if movement["amount"]["minorUnits"] <= 0:
            continue
        weeks.add(week_key(datetime.fromisoformat(movement["postedAt"])))
    return weeks


def streak_from_movements(
    movements: list[dict[str, Any]], now: datetime
) -> tuple[int, str | None]:
    weeks = contributed_weeks(movements)
    if not weeks:
        return 0, None

    offset = 0 if week_key(now) in weeks else 1
    latest = week_key(_weeks_before(now, offset))
    if latest not in weeks:
        return 0, None

    length = 0
    while length < STREAK_LOOKBACK_WEEKS and week_key(_weeks_before(now, offset + length)) in weeks:
        length += 1
    return length, latest
