from __future__ import annotations

from datetime import time


def parse_hhmm(value: str) -> time:
    """Parse a HH:MM time string. Raises ValueError on invalid input."""
    raw = value.strip()
    parts = raw.split(":")
    if len(parts) != 2:
        raise ValueError("time must be HH:MM")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError("time must contain numbers") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time is out of range")
    return time(hour=hour, minute=minute)


def parse_time_list(value: str) -> list[str]:
    """Parse a comma- or semicolon-separated list of HH:MM times.
    Returns deduplicated list preserving order. Raises ValueError if empty."""
    items = value.replace(";", ",").replace("\n", ",").split(",")
    times = [parse_hhmm(item).strftime("%H:%M") for item in items if item.strip()]
    if not times:
        raise ValueError("empty time list")
    return list(dict.fromkeys(times))


def parse_quiet_hours(value: str) -> tuple[time, time]:
    """Parse 'HH:MM - HH:MM' or 'HH:MM — HH:MM' quiet hours range."""
    normalized = value.strip().replace("—", "-").replace("–", "-")
    if "-" not in normalized:
        raise ValueError("quiet hours separator is missing")
    start_raw, end_raw = [part.strip() for part in normalized.split("-", 1)]
    return parse_hhmm(start_raw), parse_hhmm(end_raw)
