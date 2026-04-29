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
    """Parse provider time values like '05:14', '5:14' or '05:14 (+05)'."""
    text = str(value).strip()
    match = re.search(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})", text)
    if not match:
        raise ValueError(f"Invalid prayer time value: {value!r}")
    return time(hour=int(match.group("hour")), minute=int(match.group("minute")))


def _extract_times(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract prayer timings from islomapi.uz-compatible payloads.

    Supported shapes:
    - islomapi daily: {times: {tong_saharlik, peshin, asr, shom_iftor, hufton}}
    - wrapped: {data: {times: {...}}}
    - generic: a flat dict with fajr/dhuhr/asr/maghrib/isha keys
    """
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


# Bot UI stores Uzbek city names. islomapi.uz expects exact Uzbek Latin
# region names. Keep this list centralized so bot, Mini App and cache use the
# same canonical value. Unsupported custom input falls back to the stripped
# value, but all app-selectable cities are mapped here.
ISLOMAPI_REGIONS = (
    "Toshkent",
    "Andijon",
    "Buxoro",
    "Guliston",
    "Jizzax",
    "Navoiy",
    "Namangan",
    "Nukus",
    "Qarshi",
    "Samarqand",
    "Termiz",
    "Urganch",
    "Farg'ona",
)

_ISLOMAPI_REGION_ALIASES = {
    "tashkent": "Toshkent",
    "toshkent": "Toshkent",
    "toshkent shahar": "Toshkent",
    "toshkent viloyati": "Toshkent",
    "andijon": "Andijon",
    "andijan": "Andijon",
    "buxoro": "Buxoro",
    "bukhara": "Buxoro",
    "guliston": "Guliston",
    "gulistan": "Guliston",
    "sirdaryo": "Guliston",
    "syrdarya": "Guliston",
    "jizzax": "Jizzax",
    "jizzakh": "Jizzax",
    "djizak": "Jizzax",
    "navoiy": "Navoiy",
    "navoi": "Navoiy",
    "namangan": "Namangan",
    "nukus": "Nukus",
    "qoraqalpog'iston": "Nukus",
    "qoraqalpogiston": "Nukus",
    "karakalpakstan": "Nukus",
    "qarshi": "Qarshi",
    "karshi": "Qarshi",
    "qashqadaryo": "Qarshi",
    "kashkadarya": "Qarshi",
    "samarqand": "Samarqand",
    "samarkand": "Samarqand",
    "termiz": "Termiz",
    "termez": "Termiz",
    "surxondaryo": "Termiz",
    "surkhandarya": "Termiz",
    "urganch": "Urganch",
    "urgench": "Urganch",
    "xorazm": "Urganch",
    "khorezm": "Urganch",
    "farg'ona": "Farg'ona",
    "fargona": "Farg'ona",
    "fergana": "Farg'ona",
}


def _normalize_region_key(city: str) -> str:
    return str(city).strip().lower().replace('`', "'").replace("'", "'")


def _region_for_islomapi(city: str) -> str:
    normalized = _normalize_region_key(city)
    return _ISLOMAPI_REGION_ALIASES.get(normalized, str(city).strip() or "Toshkent")


def is_supported_islomapi_region(city: str) -> bool:
    return _region_for_islomapi(city) in ISLOMAPI_REGIONS

def _islomapi_api_base(base_url: str | None) -> str:
    """Normalize config to the islomapi API root.

    Accepts https://islomapi.uz, https://islomapi.uz/api, a full daily/monthly
    endpoint, or an older Aladhan value left in Railway. Older Aladhan values are
    intentionally redirected to islomapi because this bot now uses islomapi.uz.
    """
    raw = (base_url or "").strip().rstrip("/")
    if not raw:
        return "https://islomapi.uz/api"

    parsed = urlparse(raw)
    hostname = (parsed.hostname or "").lower()
    if "aladhan" in hostname:
        return "https://islomapi.uz/api"

    if hostname == "islomapi.uz" or hostname.endswith(".islomapi.uz"):
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or "islomapi.uz"
        return f"{scheme}://{netloc}/api"

    if raw.endswith("/api/daily"):
        return raw[: -len("/daily")]
    if raw.endswith("/api/monthly"):
        return raw[: -len("/monthly")]
    if raw.endswith("/api"):
        return raw
    return raw


def _extract_monthly_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "result", "items"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _parse_islomapi_date(row: dict[str, Any], *, fallback_year: int, fallback_month: int) -> date | None:
    raw = row.get("date") or row.get("sana") or row.get("day")
    if raw is None:
        return None
    if isinstance(raw, int):
        return date(fallback_year, fallback_month, raw)

    text = str(raw).strip()
    # Common islomapi shape is DD.MM.YYYY or DD.MM.
    match = re.search(r"(?P<day>\d{1,2})[.\-/](?P<month>\d{1,2})(?:[.\-/](?P<year>\d{4}))?", text)
    if match:
        return date(
            int(match.group("year") or fallback_year),
            int(match.group("month")),
            int(match.group("day")),
        )

    # Some wrappers may only return the day number as a string.
    if text.isdigit():
        return date(fallback_year, fallback_month, int(text))
    return None


class ExternalPrayerTimesProvider:
    """Fetch prayer times from islomapi.uz.

    Daily endpoint:
    GET https://islomapi.uz/api/daily?region=Toshkent&month=4&day=28

    Monthly endpoint helper:
    GET https://islomapi.uz/api/monthly?region=Toshkent&month=4
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
        return self._dto_from_times(
            city=city,
            prayer_date=day,
            timezone_name=timezone_name,
            data=data,
            raw_payload=payload,
            source=source,
        )

    async def fetch_monthly(self, city: str, month: int, year: int, timezone_name: str) -> list[PrayerTimesDTO]:
        """Fetch and parse a whole month from islomapi.uz.

        The current bot fetches single days for reminders, but this method keeps the
        provider ready for monthly prefetching without changing database schema.
        """
        base_url = settings.prayer_api_base_url.rstrip("/")
        url, params, source = self._build_monthly_request(base_url, city, month)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                resp.raise_for_status()
                payload = await resp.json()

        rows = _extract_monthly_rows(payload)
        result: list[PrayerTimesDTO] = []
        for row in rows:
            row_date = _parse_islomapi_date(row, fallback_year=year, fallback_month=month)
            if row_date is None:
                continue
            data = _extract_times(row)
            result.append(
                self._dto_from_times(
                    city=city,
                    prayer_date=row_date,
                    timezone_name=timezone_name,
                    data=data,
                    raw_payload=row,
                    source=source,
                )
            )
        return result

    @staticmethod
    def _dto_from_times(
        *,
        city: str,
        prayer_date: date,
        timezone_name: str,
        data: dict[str, Any],
        raw_payload: dict[str, Any],
        source: str,
    ) -> PrayerTimesDTO:
        return PrayerTimesDTO(
            city=city,
            prayer_date=prayer_date,
            timezone=timezone_name,
            fajr_time=_pick_time(data, "tong_saharlik", "bomdod", "fajr", "Fajr", "tong"),
            dhuhr_time=_pick_time(data, "peshin", "dhuhr", "Dhuhr", "zuhr", "Zuhr"),
            asr_time=_pick_time(data, "asr", "Asr"),
            maghrib_time=_pick_time(data, "shom_iftor", "shom", "maghrib", "Maghrib", "iftor"),
            isha_time=_pick_time(data, "hufton", "xufton", "isha", "Isha"),
            raw_payload=raw_payload,
            source=source,
        )

    @staticmethod
    def _build_request(base_url: str, city: str, day: date, timezone_name: str) -> tuple[str, dict[str, str], str]:
        api_base = _islomapi_api_base(base_url)
        url = f"{api_base}/daily"
        params = {
            "region": _region_for_islomapi(city),
            "month": str(day.month),
            "day": str(day.day),
        }
        return url, params, "islomapi_daily"

    @staticmethod
    def _build_monthly_request(base_url: str, city: str, month: int) -> tuple[str, dict[str, str], str]:
        api_base = _islomapi_api_base(base_url)
        url = f"{api_base}/monthly"
        params = {
            "region": _region_for_islomapi(city),
            "month": str(month),
        }
        return url, params, "islomapi_monthly"


class PrayerTimesService:
    def __init__(self, repo: PrayerTimesRepository, provider: PrayerTimesProvider | None = None):
        self.repo = repo
        self.provider = provider or ExternalPrayerTimesProvider()

    async def get_or_fetch(self, city: str, day: date, timezone_name: str = "Asia/Tashkent") -> PrayerTimesDTO:
        canonical_city = _region_for_islomapi(city)
        cached = await self.repo.get(canonical_city, day)
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

        dto = await self.provider.fetch(canonical_city, day, timezone_name)
        await self.repo.upsert(
            city=canonical_city,
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
