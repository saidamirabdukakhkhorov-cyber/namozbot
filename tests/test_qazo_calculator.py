from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services.qazo_calculator import QazoCalculatorService


class DummyRepo:
    pass


def test_qazo_calculator_all_prayers():
    service = QazoCalculatorService(DummyRepo(), DummyRepo())
    result = service.calculate(date(2020, 1, 1), date(2020, 1, 3), ["fajr", "dhuhr", "asr", "maghrib", "isha"])
    assert result.days_count == 3
    assert result.breakdown["fajr"] == 3
    assert result.total_count == 15


def test_qazo_calculator_subset():
    service = QazoCalculatorService(DummyRepo(), DummyRepo())
    result = service.calculate(date(2020, 1, 1), date(2020, 1, 3), ["fajr", "isha"])
    assert result.total_count == 6
    assert set(result.breakdown) == {"fajr", "isha"}


def test_qazo_calculator_deduplicates_prayers():
    service = QazoCalculatorService(DummyRepo(), DummyRepo())
    result = service.calculate(date(2020, 1, 1), date(2020, 1, 1), ["isha", "fajr", "isha", "unknown"])
    assert result.selected_prayers == ["fajr", "isha"]
    assert result.total_count == 2


def test_qazo_calculator_rejects_future_dates():
    service = QazoCalculatorService(DummyRepo(), DummyRepo())
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(ValueError):
        service.calculate(tomorrow, tomorrow, ["fajr"])
