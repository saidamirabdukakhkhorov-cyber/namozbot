from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date


def month_start(d: date) -> date:
    return d.replace(day=1)


def previous_month(d: date) -> tuple[date, date]:
    first_day_of_current_month = month_start(d)
    last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
    return month_start(last_day_of_previous_month), last_day_of_previous_month


def current_month_range(today: date | None = None) -> tuple[date, date]:
    """Return the current month range from the first day of the month to today."""
    today = today or date.today()
    return month_start(today), today


def period_by_key(key: str, today: date | None = None) -> Period:
    today = today or date.today()

    if key == "today":
        return Period(key, today, today)

    if key == "yesterday":
        yesterday = today - timedelta(days=1)
        return Period(key, yesterday, yesterday)

    if key == "this_week":
        start = today - timedelta(days=today.weekday())
        return Period(key, start, today)

    if key == "last_week":
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return Period(key, start, end)

    if key == "this_month":
        start, end = current_month_range(today)
        return Period(key, start, end)

    if key == "last_month":
        start, end = previous_month(today)
        return Period(key, start, end)

    if key == "this_year":
        return Period(key, date(today.year, 1, 1), today)

    if key == "last_year":
        return Period(key, date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))

    start, end = current_month_range(today)
    return Period("this_month", start, end)
