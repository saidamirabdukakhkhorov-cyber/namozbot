from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp

from app.core.config import settings
from app.core.constants import PRAYER_NAMES
from app.db.repositories.prayer_times import PrayerTimesRepository


@dataclass(frozen=True)
class PrayerTimesDTO:
    city: str
    prayer_date: date
    timezone: str
    fajr_time: time
    dhuhr_time: time
    asr_time: time
    maghrib_time: time
    isha_time: time
    raw_payload: dict[str, Any]
    source: str = "external"

    def as_dict(self) -> dict[str, time]:
        return {name: getattr(self, f"{name}_time") for name in PRAYER_NAMES}


class PrayerTimesProvider(Protocol):
    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO: ...


def _parse_hhmm(value: Any) -> time:
    text = str(value).strip()[:5]
    return datetime.strptime(text, "%H:%M").time()


def _extract_times(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("times"), dict):
        return payload["times"]
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("times"), dict):
            return data["times"]
        return data
    return payload


def _pick_time(data: dict[str, Any], *keys: str) -> time:
    lower_map = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = data.get(key)
        if value is None:
            value = lower_map.get(key.lower())
        if value:
            return _parse_hhmm(value)
    raise KeyError(f"Prayer time key not found. Tried: {', '.join(keys)}")


class ExternalPrayerTimesProvider:
    """Fetch prayer times from a configurable provider.

    Supports both a generic endpoint that returns fajr/dhuhr/asr/maghrib/isha and
    islomapi.uz, whose public response uses Uzbek field names:
    tong_saharlik, peshin, asr, shom_iftor, hufton.
    """

    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO:
        base_url = settings.prayer_api_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError("PRAYER_API_BASE_URL is not configured")

        url, params = self._build_request(base_url, city, day)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        data = _extract_times(payload)
        return PrayerTimesDTO(
            city=city,
            prayer_date=day,
            timezone=timezone_name,
            fajr_time=_pick_time(data, "fajr", "bomdod", "tong_saharlik", "tong"),
            dhuhr_time=_pick_time(data, "dhuhr", "zuhr", "peshin"),
            asr_time=_pick_time(data, "asr"),
            maghrib_time=_pick_time(data, "maghrib", "shom", "shom_iftor", "iftor"),
            isha_time=_pick_time(data, "isha", "hufton", "xufton"),
            raw_payload=payload,
        )

    @staticmethod
    def _build_request(base_url: str, city: str, day: date) -> tuple[str, dict[str, str]]:
        parsed = urlparse(base_url)
        hostname = parsed.hostname or ""

        if "islomapi.uz" in hostname:
            # islomapi.uz endpoint format: /api/present/day?region=Toshkent
            # Its present/day endpoint returns current-day times; the date is not
            # supported there, but keeping day in the signature preserves the app API.
            if parsed.path and parsed.path != "/":
                url = base_url
            else:
                url = f"{base_url}/api/present/day"
            return url, {"region": city}

        return base_url, {"city": city, "date": day.isoformat()}


class PrayerTimesService:
    def __init__(self, repo: PrayerTimesRepository, provider: PrayerTimesProvider | None = None):
        self.repo = repo
        self.provider = provider or ExternalPrayerTimesProvider()

    async def get_or_fetch(self, city: str, day: date, timezone_name: str = "Asia/Tashkent") -> PrayerTimesDTO:
        cached = await self.repo.get(city, day)
        if cached:
            return PrayerTimesDTO(
                cached.city,
                cached.prayer_date,
                cached.timezone,
                cached.fajr_time,
                cached.dhuhr_time,
                cached.asr_time,
                cached.maghrib_time,
                cached.isha_time,
                cached.raw_payload,
                cached.source,
            )

        dto = await self.provider.fetch(city, day, timezone_name)
        await self.repo.upsert(
            city=city,
            prayer_date=day,
            timezone_name=timezone_name,
            fajr_time=dto.fajr_time,
            dhuhr_time=dto.dhuhr_time,
            asr_time=dto.asr_time,
            maghrib_time=dto.maghrib_time,
            isha_time=dto.isha_time,
            source=dto.source,
            raw_payload=dto.raw_payload,
        )
        return dto

    @staticmethod
    def combine(day: date, prayer_time: time, timezone_name: str) -> datetime:
        return datetime.combine(day, prayer_time, tzinfo=ZoneInfo(timezone_name))
