from __future__ import annotations

import re
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
    """Parse provider time values like '05:14', '05:14 (+05)' or '5:14'."""
    text = str(value).strip()
    match = re.search(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})", text)
    if not match:
        raise ValueError(f"Invalid prayer time value: {value!r}")
    return time(hour=int(match.group("hour")), minute=int(match.group("minute")))


def _extract_times(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract prayer timings from supported providers.

    Supported shapes:
    - Aladhan: {data: {timings: {Fajr, Dhuhr, Asr, Maghrib, Isha}}}
    - islomapi.uz: {times: {...}} or {data: {times: {...}}}
    - generic: a flat dict with fajr/dhuhr/asr/maghrib/isha keys
    """
    if isinstance(payload.get("times"), dict):
        return payload["times"]

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("timings"), dict):
            return data["timings"]
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


_ALADHAN_CITY_ALIASES = {
    # Bot UI keeps Uzbek city names, while Aladhan resolves city names more
    # reliably in English transliteration. Custom city names are sent as-is.
    "toshkent": "Tashkent",
    "samarqand": "Samarkand",
    "buxoro": "Bukhara",
    "andijon": "Andijan",
    "farg'ona": "Fergana",
    "farg‘ona": "Fergana",
    "fargona": "Fergana",
    "namangan": "Namangan",
    "qarshi": "Qarshi",
    "nukus": "Nukus",
}


def _city_for_aladhan(city: str) -> str:
    normalized = str(city).strip().lower().replace("ʻ", "'").replace("ʼ", "'")
    return _ALADHAN_CITY_ALIASES.get(normalized, str(city).strip())


def _aladhan_api_base(base_url: str) -> str:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()

    if hostname == "aladhan.com" or hostname.endswith(".aladhan.com"):
        # User may configure either https://aladhan.com, https://api.aladhan.com
        # or https://api.aladhan.com/v1. The actual API base is /v1.
        scheme = parsed.scheme or "https"
        api_host = "api.aladhan.com"
        path = parsed.path.rstrip("/")
        if not path or path == "/":
            return f"{scheme}://{api_host}/v1"
        if path.endswith("/v1"):
            return f"{scheme}://{api_host}{path}"
        if "/v1" in path:
            return f"{scheme}://{api_host}{path.split('/v1', 1)[0]}/v1"
        return f"{scheme}://{api_host}/v1"

    return base_url.rstrip("/")


class ExternalPrayerTimesProvider:
    """Fetch prayer times from Aladhan or a backward-compatible provider.

    Primary provider: Aladhan Prayer Times API. The integration uses
    /timingsByCity/{date} with city, country and timezone parameters.

    Backward compatibility with islomapi.uz is kept only so older local configs do
    not fail unexpectedly; production should use PRAYER_API_BASE_URL pointing to
    Aladhan.
    """

    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO:
        base_url = settings.prayer_api_base_url.rstrip("/")
        if not base_url:
            raise RuntimeError("PRAYER_API_BASE_URL is not configured")

        url, params, source = self._build_request(base_url, city, day, timezone_name)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        data = _extract_times(payload)
        return PrayerTimesDTO(
            city=city,
            prayer_date=day,
            timezone=timezone_name,
            fajr_time=_pick_time(data, "Fajr", "fajr", "bomdod", "tong_saharlik", "tong"),
            dhuhr_time=_pick_time(data, "Dhuhr", "dhuhr", "Zuhr", "zuhr", "peshin"),
            asr_time=_pick_time(data, "Asr", "asr"),
            maghrib_time=_pick_time(data, "Maghrib", "maghrib", "shom", "shom_iftor", "iftor"),
            isha_time=_pick_time(data, "Isha", "isha", "hufton", "xufton"),
            raw_payload=payload,
            source=source,
        )

    @staticmethod
    def _build_request(base_url: str, city: str, day: date, timezone_name: str) -> tuple[str, dict[str, str], str]:
        parsed = urlparse(base_url)
        hostname = (parsed.hostname or "").lower()

        if "aladhan" in hostname:
            api_base = _aladhan_api_base(base_url)
            url = f"{api_base}/timingsByCity/{day.strftime('%d-%m-%Y')}"
            params = {
                "city": _city_for_aladhan(city),
                "country": settings.prayer_api_country or "Uzbekistan",
                "timezonestring": timezone_name or settings.default_timezone,
            }
            if settings.prayer_api_method:
                params["method"] = settings.prayer_api_method
            if settings.prayer_api_school:
                params["school"] = settings.prayer_api_school
            return url, params, "aladhan"

        if "islomapi.uz" in hostname:
            # Deprecated fallback. islomapi.uz present/day returns only current day.
            url = base_url if parsed.path and parsed.path != "/" else f"{base_url}/api/present/day"
            return url, {"region": city}, "islomapi"

        return base_url, {"city": city, "date": day.isoformat()}, "external"


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
