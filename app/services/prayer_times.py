from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp

_HTTP_TIMEOUT = aiohttp.ClientTimeout(total=4, connect=2, sock_read=3)

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
    text = str(value or "").strip()
    match = re.search(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})", text)
    if not match:
        raise ValueError(f"Invalid prayer time value: {value!r}")
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        raise ValueError(f"Prayer time is out of range: {value!r}")
    return time(hour=hour, minute=minute)


def _extract_times(payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    """Extract prayer timings from islomapi.uz-compatible payloads.

    Supported shapes:
    - islomapi daily: {times: {tong_saharlik, peshin, asr, shom_iftor, hufton}}
    - wrapped: {data: {times: {...}}}
    - generic: a flat dict with fajr/dhuhr/asr/maghrib/isha keys
    """
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("times"), dict):
        return payload["times"]

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("times"), dict):
            return data["times"]
        return data

    return payload


def _pick_time(data: dict[str, Any], *keys: str) -> time:
    lower_map = {str(key).lower(): value for key, value in (data or {}).items()}
    for key in keys:
        value = (data or {}).get(key)
        if value is None:
            value = lower_map.get(key.lower())
        if value not in (None, ""):
            return _parse_hhmm(value)
    raise KeyError(f"Prayer time key not found. Tried: {', '.join(keys)}")


# islomapi.uz expects exact Uzbek Latin region names. Keep this list centralized
# so bot, Mini App and cache use the same canonical value.
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
    "ташкент": "Toshkent",
    "andijon": "Andijon",
    "andijan": "Andijon",
    "андижон": "Andijon",
    "buxoro": "Buxoro",
    "bukhara": "Buxoro",
    "бухоро": "Buxoro",
    "guliston": "Guliston",
    "gulistan": "Guliston",
    "sirdaryo": "Guliston",
    "syrdarya": "Guliston",
    "сирдарё": "Guliston",
    "jizzax": "Jizzax",
    "jizzakh": "Jizzax",
    "djizak": "Jizzax",
    "жиззах": "Jizzax",
    "navoiy": "Navoiy",
    "navoi": "Navoiy",
    "навоий": "Navoiy",
    "namangan": "Namangan",
    "наманган": "Namangan",
    "nukus": "Nukus",
    "qoraqalpog'iston": "Nukus",
    "qoraqalpogiston": "Nukus",
    "karakalpakstan": "Nukus",
    "қорақалпоғистон": "Nukus",
    "qarshi": "Qarshi",
    "karshi": "Qarshi",
    "qashqadaryo": "Qarshi",
    "kashkadarya": "Qarshi",
    "қарши": "Qarshi",
    "samarqand": "Samarqand",
    "samarkand": "Samarqand",
    "самарқанд": "Samarqand",
    "termiz": "Termiz",
    "termez": "Termiz",
    "surxondaryo": "Termiz",
    "surkhandarya": "Termiz",
    "термиз": "Termiz",
    "urganch": "Urganch",
    "urgench": "Urganch",
    "xorazm": "Urganch",
    "khorezm": "Urganch",
    "урганч": "Urganch",
    "farg'ona": "Farg'ona",
    "fargona": "Farg'ona",
    "fergana": "Farg'ona",
    "фарғона": "Farg'ona",
    "фаргона": "Farg'ona",
}


def _normalize_region_key(city: str) -> str:
    text = unicodedata.normalize("NFKC", str(city or "")).strip().lower()
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'").replace("ʼ", "'").replace("ʻ", "'")
    text = text.replace("-", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def _region_for_islomapi(city: str) -> str:
    normalized = _normalize_region_key(city)
    if normalized in _ISLOMAPI_REGION_ALIASES:
        return _ISLOMAPI_REGION_ALIASES[normalized]
    # Normalize exact canonical values that may include curly apostrophes.
    for region in ISLOMAPI_REGIONS:
        if _normalize_region_key(region) == normalized:
            return region
    return "Toshkent"


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
        try:
            return date(fallback_year, fallback_month, raw)
        except ValueError:
            return None

    text = str(raw).strip()
    # islomapi shape is often YYYY-MM-DDT... or DD.MM.YYYY.
    iso_match = re.search(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})", text)
    if iso_match:
        try:
            return date(int(iso_match.group("year")), int(iso_match.group("month")), int(iso_match.group("day")))
        except ValueError:
            return None

    match = re.search(r"(?P<day>\d{1,2})[.\-/](?P<month>\d{1,2})(?:[.\-/](?P<year>\d{4}))?", text)
    if match:
        try:
            return date(
                int(match.group("year") or fallback_year),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            return None

    if text.isdigit():
        try:
            return date(fallback_year, fallback_month, int(text))
        except ValueError:
            return None
    return None


class ExternalPrayerTimesProvider:
    """Fetch prayer times from islomapi.uz.

    Daily endpoint:
    GET https://islomapi.uz/api/daily?region=Toshkent&month=4&day=28

    Monthly endpoint helper/fallback:
    GET https://islomapi.uz/api/monthly?region=Toshkent&month=4
    """

    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO:
        base_url = settings.prayer_api_base_url.rstrip("/") or "https://islomapi.uz"
        daily_exc: Exception | None = None
        try:
            url, params, source = self._build_request(base_url, city, day, timezone_name)
            payload = await self._get_json(url, params)
            data = _extract_times(payload)
            return self._dto_from_times(
                city=_region_for_islomapi(city),
                prayer_date=day,
                timezone_name=timezone_name,
                data=data,
                raw_payload=payload if isinstance(payload, dict) else {"payload": payload},
                source=source,
            )
        except Exception as exc:
            daily_exc = exc

        # Daily can fail for provider-side reasons. Monthly usually has the same
        # data and gives us a safe fallback without switching providers.
        try:
            month_rows = await self.fetch_monthly(city, day.month, day.year, timezone_name)
            for dto in month_rows:
                if dto.prayer_date.day == day.day:
                    payload = dict(dto.raw_payload or {})
                    payload.setdefault("fallback_from", "daily")
                    payload.setdefault("daily_error", str(daily_exc))
                    return PrayerTimesDTO(
                        city=dto.city,
                        prayer_date=day,
                        timezone=dto.timezone,
                        fajr_time=dto.fajr_time,
                        dhuhr_time=dto.dhuhr_time,
                        asr_time=dto.asr_time,
                        maghrib_time=dto.maghrib_time,
                        isha_time=dto.isha_time,
                        raw_payload=payload,
                        source="islomapi_monthly_fallback",
                    )
        except Exception:
            pass
        raise daily_exc or RuntimeError("Prayer times provider failed")

    async def _get_json(self, url: str, params: dict[str, str]) -> Any:
        async with aiohttp.ClientSession(timeout=_HTTP_TIMEOUT) as session:
            async with session.get(url, params=params) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)

    async def fetch_monthly(self, city: str, month: int, year: int, timezone_name: str) -> list[PrayerTimesDTO]:
        base_url = settings.prayer_api_base_url.rstrip("/") or "https://islomapi.uz"
        url, params, source = self._build_monthly_request(base_url, city, month)
        payload = await self._get_json(url, params)
        rows = _extract_monthly_rows(payload)
        result: list[PrayerTimesDTO] = []
        for row in rows:
            row_date = _parse_islomapi_date(row, fallback_year=year, fallback_month=month)
            if row_date is None:
                continue
            # islomapi does not accept a year parameter, so force cache key/date to
            # the requested year while keeping the provider payload intact.
            row_date = date(year, row_date.month, row_date.day)
            data = _extract_times(row)
            result.append(
                self._dto_from_times(
                    city=_region_for_islomapi(city),
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
            city=_region_for_islomapi(city),
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
            cached_values = (
                cached.fajr_time,
                cached.dhuhr_time,
                cached.asr_time,
                cached.maghrib_time,
                cached.isha_time,
            )
            # Older production rows may be incomplete after a failed migration or
            # a provider outage. Do not return them to the Mini App as bot data;
            # re-fetch and overwrite the cache instead.
            if all(cached_values):
                return PrayerTimesDTO(
                    cached.city,
                    cached.prayer_date,
                    cached.timezone,
                    cached.fajr_time,
                    cached.dhuhr_time,
                    cached.asr_time,
                    cached.maghrib_time,
                    cached.isha_time,
                    cached.raw_payload if isinstance(cached.raw_payload, dict) else {"payload": cached.raw_payload},
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
