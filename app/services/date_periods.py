from dataclasses import dataclass
from datetime import date, timedelta
@dataclass(frozen=True)
class Period: key: str; start: date; end: date
def month_start(d: date) -> date: return d.replace(day=1)
def previous_month(d: date):
    first = month_start(d); last = first - timedelta(days=1); return month_start(last), last
def period_by_key(key: str, today: date | None = None) -> Period:
    today = today or date.today()
    if key == "today": return Period(key, today, today)
    if key == "yesterday": y = today - timedelta(days=1); return Period(key, y, y)
    if key == "this_week": start = today - timedelta(days=today.weekday()); return Period(key, start, today)
    if key == "last_week": end = today - timedelta(days=today.weekday()+1); return Period(key, end - timedelta(days=6), end)
    if key == "this_month": return Period(key, month_start(today), today)
    if key == "last_month": start, end = previous_month(today); return Period(key, start, end)
    if key == "this_year": return Period(key, date(today.year,1,1), today)
    if key == "last_year": return Period(key, date(today.year-1,1,1), date(today.year-1,12,31))
    return Period("this_month", month_start(today), today)
