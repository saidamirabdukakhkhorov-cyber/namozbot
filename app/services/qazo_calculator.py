from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.constants import PRAYER_NAMES
from app.services.timezone import tashkent_today


@dataclass(frozen=True)
class QazoCalculationPreview:
    start_date: date
    end_date: date
    selected_prayers: list[str]
    days_count: int
    breakdown: dict[str, int]
    total_count: int


class QazoCalculatorService:
    def __init__(self, calculations_repo, missed_repo):
        self.calculations_repo = calculations_repo
        self.missed_repo = missed_repo

    @staticmethod
    def _normalize_prayers(selected_prayers: list[str]) -> list[str]:
        selected_set = {p for p in selected_prayers if p in PRAYER_NAMES}
        return [p for p in PRAYER_NAMES if p in selected_set]

    def calculate(self, start_date: date, end_date: date, selected_prayers: list[str]) -> QazoCalculationPreview:
        today = tashkent_today()
        if start_date > today or end_date > today:
            raise ValueError("Kelajak sanalari bo'yicha qazo hisoblab bo'lmaydi")
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date")

        selected = self._normalize_prayers(selected_prayers)
        if not selected:
            raise ValueError("Select at least one prayer")

        days = (end_date - start_date).days + 1
        breakdown = {p: days for p in selected}
        return QazoCalculationPreview(start_date, end_date, selected, days, breakdown, days * len(selected))

    async def save_preview(self, user_id: int, preview: QazoCalculationPreview):
        return await self.calculations_repo.create_calculated(
            user_id=user_id,
            start_date=preview.start_date,
            end_date=preview.end_date,
            selected_prayers=preview.selected_prayers,
            days_count=preview.days_count,
            breakdown=preview.breakdown,
        )

    async def apply(
        self,
        *,
        user_id: int,
        calculation_id: int,
        start_date: date,
        end_date: date,
        selected_prayers: list[str],
    ):
        preview = self.calculate(start_date, end_date, selected_prayers)
        created = {p: 0 for p in preview.selected_prayers}
        skipped = {p: 0 for p in preview.selected_prayers}
        day = start_date

        while day <= end_date:
            for prayer in preview.selected_prayers:
                _, ok = await self.missed_repo.create(
                    user_id=user_id,
                    prayer_name=prayer,
                    prayer_date=day,
                    source="calculator",
                    qazo_calculation_id=calculation_id,
                )
                if ok:
                    created[prayer] += 1
                else:
                    skipped[prayer] += 1
            day += timedelta(days=1)

        await self.calculations_repo.mark_applied(calculation_id, created, skipped)
        return created, skipped
