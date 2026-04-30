from datetime import date, time
from typing import Any

from sqlalchemy import select

from app.db.models import PrayerTime
from app.db.repositories.base import BaseRepository


class PrayerTimesRepository(BaseRepository):
    async def get(self, city: str, prayer_date: date):
        return await self.session.scalar(
            select(PrayerTime).where(
                PrayerTime.city == city,
                PrayerTime.prayer_date == prayer_date,
            )
        )

    async def upsert(
        self,
        *,
        city: str,
        prayer_date: date,
        timezone_name: str,
        fajr_time: time,
        dhuhr_time: time,
        asr_time: time,
        maghrib_time: time,
        isha_time: time,
        source: str,
        raw_payload: dict[str, Any] | None = None,
    ):
        values = dict(
            timezone=timezone_name,
            fajr_time=fajr_time,
            dhuhr_time=dhuhr_time,
            asr_time=asr_time,
            maghrib_time=maghrib_time,
            isha_time=isha_time,
            source=source,
            raw_payload=raw_payload or {},
        )
        row = await self.get(city, prayer_date)
        if row:
            for key, value in values.items():
                setattr(row, key, value)
            await self.session.flush()
            return row

        row = PrayerTime(city=city, prayer_date=prayer_date, **values)
        self.session.add(row)
        await self.session.flush()
        return row
