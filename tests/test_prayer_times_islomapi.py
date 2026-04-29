from datetime import date, time

from app.services.prayer_times import (
    ExternalPrayerTimesProvider,
    ISLOMAPI_REGIONS,
    _extract_times,
    _islomapi_api_base,
    _parse_hhmm,
    _pick_time,
    _region_for_islomapi,
    is_supported_islomapi_region,
)


def test_islomapi_base_is_normalized():
    assert _islomapi_api_base("https://islomapi.uz") == "https://islomapi.uz/api"
    assert _islomapi_api_base("https://islomapi.uz/api") == "https://islomapi.uz/api"
    assert _islomapi_api_base("https://islomapi.uz/api/daily") == "https://islomapi.uz/api"
    assert _islomapi_api_base("https://api.aladhan.com/v1") == "https://islomapi.uz/api"


def test_city_names_are_mapped_for_islomapi():
    assert _region_for_islomapi("Toshkent") == "Toshkent"
    assert _region_for_islomapi("Tashkent") == "Toshkent"
    assert _region_for_islomapi("Samarkand") == "Samarqand"
    assert _region_for_islomapi("Bukhara") == "Buxoro"
    assert _region_for_islomapi("Fergana") == "Farg'ona"
    assert _region_for_islomapi("Farg‘ona") == "Farg'ona"
    assert _region_for_islomapi("Farg’ona") == "Farg'ona"
    assert _region_for_islomapi("Unknown city") == "Toshkent"
    assert _region_for_islomapi("Sirdaryo") == "Guliston"
    assert _region_for_islomapi("Xorazm") == "Urganch"
    assert _region_for_islomapi("Surxondaryo") == "Termiz"
    assert _region_for_islomapi("Qoraqalpogiston") == "Nukus"


def test_all_app_selectable_regions_are_supported_for_islomapi():
    assert len(ISLOMAPI_REGIONS) >= 13
    for region in ISLOMAPI_REGIONS:
        assert is_supported_islomapi_region(region)
        url, params, source = ExternalPrayerTimesProvider._build_request(
            "https://islomapi.uz",
            region,
            date(2026, 4, 28),
            "Asia/Tashkent",
        )
        assert source == "islomapi_daily"
        assert url == "https://islomapi.uz/api/daily"
        assert params["region"] == region
        assert params["month"] == "4"
        assert params["day"] == "28"


def test_islomapi_daily_request_uses_daily_endpoint_with_region_month_day():
    url, params, source = ExternalPrayerTimesProvider._build_request(
        "https://islomapi.uz",
        "Toshkent",
        date(2026, 4, 28),
        "Asia/Tashkent",
    )

    assert source == "islomapi_daily"
    assert url == "https://islomapi.uz/api/daily"
    assert params == {"region": "Toshkent", "month": "4", "day": "28"}


def test_islomapi_monthly_request_uses_monthly_endpoint_with_region_month():
    url, params, source = ExternalPrayerTimesProvider._build_monthly_request(
        "https://islomapi.uz",
        "Toshkent",
        4,
    )

    assert source == "islomapi_monthly"
    assert url == "https://islomapi.uz/api/monthly"
    assert params == {"region": "Toshkent", "month": "4"}


def test_islomapi_payload_times_are_extracted_and_parsed():
    payload = {
        "region": "Toshkent",
        "date": "28.04.2026",
        "weekday": "Seshanba",
        "times": {
            "tong_saharlik": "04:12",
            "quyosh": "05:35",
            "peshin": "12:25",
            "asr": "16:55",
            "shom_iftor": "19:18",
            "hufton": "20:42",
        },
    }

    data = _extract_times(payload)
    assert _pick_time(data, "tong_saharlik", "bomdod") == time(4, 12)
    assert _pick_time(data, "peshin") == time(12, 25)
    assert _pick_time(data, "asr") == time(16, 55)
    assert _pick_time(data, "shom_iftor", "shom") == time(19, 18)
    assert _pick_time(data, "hufton", "xufton") == time(20, 42)
    assert _parse_hhmm("5:07") == time(5, 7)
