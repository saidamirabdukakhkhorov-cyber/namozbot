from datetime import date, time

from app.services.prayer_times import (
    ExternalPrayerTimesProvider,
    _aladhan_api_base,
    _city_for_aladhan,
    _extract_times,
    _parse_hhmm,
    _pick_time,
)


def test_aladhan_base_is_normalized_from_site_url():
    assert _aladhan_api_base("https://aladhan.com") == "https://api.aladhan.com/v1"
    assert _aladhan_api_base("https://api.aladhan.com") == "https://api.aladhan.com/v1"
    assert _aladhan_api_base("https://api.aladhan.com/v1") == "https://api.aladhan.com/v1"


def test_uzbek_city_names_are_mapped_for_aladhan():
    assert _city_for_aladhan("Toshkent") == "Tashkent"
    assert _city_for_aladhan("Samarqand") == "Samarkand"
    assert _city_for_aladhan("Buxoro") == "Bukhara"
    assert _city_for_aladhan("Farg'ona") == "Fergana"


def test_aladhan_request_uses_timings_by_city_with_date_country_timezone():
    url, params, source = ExternalPrayerTimesProvider._build_request(
        "https://aladhan.com",
        "Toshkent",
        date(2026, 4, 28),
        "Asia/Tashkent",
    )

    assert source == "aladhan"
    assert url == "https://api.aladhan.com/v1/timingsByCity/28-04-2026"
    assert params["city"] == "Tashkent"
    assert params["country"] == "Uzbekistan"
    assert params["timezonestring"] == "Asia/Tashkent"


def test_aladhan_payload_timings_are_extracted_and_parsed():
    payload = {
        "code": 200,
        "status": "OK",
        "data": {
            "timings": {
                "Fajr": "04:12 (+05)",
                "Dhuhr": "12:25 (+05)",
                "Asr": "16:55 (+05)",
                "Maghrib": "19:18 (+05)",
                "Isha": "20:42 (+05)",
            }
        },
    }

    data = _extract_times(payload)
    assert _pick_time(data, "Fajr") == time(4, 12)
    assert _pick_time(data, "Dhuhr") == time(12, 25)
    assert _parse_hhmm("5:07") == time(5, 7)
