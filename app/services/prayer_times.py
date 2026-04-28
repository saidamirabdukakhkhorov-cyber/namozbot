from __future__ import annotations

import json
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


def _normalize_city(city: str) -> str:
    return (
        city.strip()
        .replace("‘", "'")
        .replace("’", "'")
        .replace("`", "'")
    )


def _parse_hhmm(value: Any) -> time:
    text = str(value).strip()
    # Handles "06:02", "06:02:00", "06:02 (UTC+5)".
    text = text[:5]
    return datetime.strptime(text, "%H:%M").time()


def _extract_times(payload: dict[str, Any]) -> dict[str, Any]:
    """Support common public prayer API response shapes."""
    if isinstance(payload.get("times"), dict):
        return payload["times"]

    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("times"), dict):
            return data["times"]
        return data

    if isinstance(payload.get("response"), dict):
        response = payload["response"]
        if isinstance(response.get("times"), dict):
            return response["times"]
        return response

    # Some APIs return {"response": [{...}]}.
    if isinstance(payload.get("response"), list) and payload["response"]:
        first = payload["response"][0]
        if isinstance(first, dict):
            if isinstance(first.get("times"), dict):
                return first["times"]
            return first

    return payload


def _pick_time(data: dict[str, Any], *keys: str) -> time:
    lower_map = {str(key).lower(): value for key, value in data.items()}

    for key in keys:
        value = data.get(key)
        if value is None:
            value = lower_map.get(key.lower())
        if value not in (None, ""):
            return _parse_hhmm(value)

    available = ", ".join(str(k) for k in data.keys())
    raise KeyError(f"Prayer time key not found. Tried: {', '.join(keys)}. Available: {available}")


class ExternalPrayerTimesProvider:
    """Fetch prayer times from configured API.

    Supported by default:
    - https://islomapi.uz
    - https://islomapi.uz/api/present/day
    - generic endpoint returning fajr/dhuhr/asr/maghrib/isha
    """

    async def fetch(self, city: str, day: date, timezone_name: str) -> PrayerTimesDTO:
        base_url = (settings.prayer_api_base_url or "").strip().rstrip("/")
        if not base_url:
            raise RuntimeError("PRAYER_API_BASE_URL is not configured")

        city = _normalize_city(city)
        url, params = self._build_request(base_url, city, day)
        payload = await self._get_json(url, params)
        data = _extract_times(payload)

        return PrayerTimesDTO(
            city=city,
            prayer_date=day,
            timezone=timezone_name,
            fajr_time=_pick_time(data, "fajr", "bomdod", "tong_saharlik", "tong"),
            dhuhr_time=_pick_time(data, "dhuhr", "zuhr", "zhuhr", "peshin"),
            asr_time=_pick_time(data, "asr"),
            maghrib_time=_pick_time(data, "maghrib", "shom", "shom_iftor", "iftor"),
            isha_time=_pick_time(data, "isha", "hufton", "xufton"),
            raw_payload=payload,
        )

    async def _get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "namoz-qazo-bot/1.0",
        }
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Prayer API HTTP {resp.status}: {text[:300]}")
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Prayer API returned non-JSON response: {text[:300]}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"Prayer API returned unsupported payload type: {type(payload).__name__}")
        return payload

    @staticmethod
    def _build_request(base_url: str, city: str, day: date) -> tuple[str, dict[str, str]]:
        parsed = urlparse(base_url)
        hostname = parsed.hostname or ""
        path = (parsed.path or "").rstrip("/")

        if "islomapi.uz" in hostname:
            # islomapi.uz endpoint format:
            # https://islomapi.uz/api/present/day?region=Toshkent
            if path.endswith("/api/present/day") or path.endswith("/present/day"):
                url = base_url
            else:
                url = f"{base_url}/api/present/day"
            return url, {"region": city}

        # Generic fallback endpoint format.
        return base_url, {"city": city, "date": day.isoformat()}


class PrayerTimesService:
    def __init__(self, repo: PrayerTimesRepository, provider: PrayerTimesProvider | None = None):
        self.repo = repo
        self.provider = provider or ExternalPrayerTimesProvider()

    async def get_or_fetch(self, city: str, day: date, timezone_name: str = "Asia/Tashkent") -> PrayerTimesDTO:
        city = _normalize_city(city)
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
