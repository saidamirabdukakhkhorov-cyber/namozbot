from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo
import aiohttp
from app.core.config import settings
from app.core.constants import PRAYER_NAMES
from app.db.repositories.prayer_times import PrayerTimesRepository
@dataclass(frozen=True)
class PrayerTimesDTO:
    city: str; prayer_date: date; timezone: str; fajr_time: time; dhuhr_time: time; asr_time: time; maghrib_time: time; isha_time: time; raw_payload: dict; source: str = "external"
    def as_dict(self): return {name: getattr(self, f"{name}_time") for name in PRAYER_NAMES}
class PrayerTimesProvider(Protocol):
    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO: ...
class ExternalPrayerTimesProvider:
    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO:
        if not settings.prayer_api_base_url: raise RuntimeError("PRAYER_API_BASE_URL is not configured")
        async with aiohttp.ClientSession() as session:
            async with session.get(settings.prayer_api_base_url, params={"city": city, "date": day.isoformat()}, timeout=15) as resp:
                resp.raise_for_status(); payload = await resp.json()
        data = payload.get("times") or payload.get("data") or payload
        def parse_time(*keys):
            for key in keys:
                value = data.get(key)
                if value: return datetime.strptime(str(value)[:5], "%H:%M").time()
            raise KeyError(keys[0])
        return PrayerTimesDTO(city, day, timezone_name, parse_time("fajr","bomdod"), parse_time("dhuhr","peshin"), parse_time("asr"), parse_time("maghrib","shom"), parse_time("isha","hufton"), payload)
class PrayerTimesService:
    def __init__(self, repo: PrayerTimesRepository, provider: PrayerTimesProvider | None = None): self.repo = repo; self.provider = provider or ExternalPrayerTimesProvider()
    async def get_or_fetch(self, city: str, day: date, timezone_name: str = "Asia/Tashkent"):
        cached = await self.repo.get(city, day)
        if cached: return PrayerTimesDTO(cached.city, cached.prayer_date, cached.timezone, cached.fajr_time, cached.dhuhr_time, cached.asr_time, cached.maghrib_time, cached.isha_time, cached.raw_payload, cached.source)
        dto = await self.provider.fetch(city, day, timezone_name)
        await self.repo.upsert(city=city, prayer_date=day, timezone_name=timezone_name, fajr_time=dto.fajr_time, dhuhr_time=dto.dhuhr_time, asr_time=dto.asr_time, maghrib_time=dto.maghrib_time, isha_time=dto.isha_time, source=dto.source, raw_payload=dto.raw_payload)
        return dto
    @staticmethod
    def combine(day: date, prayer_time: time, timezone_name: str): return datetime.combine(day, prayer_time, tzinfo=ZoneInfo(timezone_name))
