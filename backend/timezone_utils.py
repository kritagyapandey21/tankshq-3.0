"""IANA timezone validation and searchable metadata."""

from datetime import datetime, timezone as utc_timezone
from importlib import resources
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TIMEZONE = "Asia/Kolkata"

_COUNTRY_NAMES = {
    "AU": "Australia", "BD": "Bangladesh", "BR": "Brazil", "CA": "Canada",
    "FI": "Finland", "GB": "United Kingdom", "IN": "India", "KE": "Kenya",
    "NG": "Nigeria", "PH": "Philippines", "PK": "Pakistan", "RU": "Russia",
    "UA": "Ukraine", "UG": "Uganda", "US": "United States", "ZA": "South Africa",
    "AE": "United Arab Emirates", "JP": "Japan", "DE": "Germany", "FR": "France",
    "SG": "Singapore", "NZ": "New Zealand", "MX": "Mexico", "ES": "Spain",
}


def is_valid_timezone(name: str) -> bool:
    if not isinstance(name, str) or name not in available_timezones():
        return False
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def normalize_timezone(name: str | None) -> str:
    return name if is_valid_timezone(name or "") else DEFAULT_TIMEZONE


def _country_codes_by_zone() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    try:
        zone_tab = resources.files("tzdata").joinpath("zoneinfo", "zone.tab").read_text()
    except (ModuleNotFoundError, FileNotFoundError):
        return result
    for line in zone_tab.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 3:
            result[fields[2]] = fields[0].split(",")
    return result


_COUNTRY_CODES = _country_codes_by_zone()


def _city_label(name: str) -> str:
    city = name.split("/")[-1].replace("_", " ")
    return city.replace("St ", "St. ")


def _metadata(name: str, now: datetime) -> dict:
    local = now.astimezone(ZoneInfo(name))
    offset = local.utcoffset() or utc_timezone.utc.utcoffset(now)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    minutes = abs(total_minutes)
    offset_label = f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"
    codes = _COUNTRY_CODES.get(name, [])
    countries = [_COUNTRY_NAMES.get(code, code) for code in codes]
    country = ", ".join(countries) if countries else ""
    return {
        "id": name,
        "country": country,
        "city": _city_label(name),
        "offset": offset_label,
        "abbreviation": local.tzname() or name,
        "search": " ".join([country, _city_label(name), name, offset_label, local.tzname() or ""]).lower(),
    }


def timezone_catalog() -> list[dict]:
    now = datetime.now(utc_timezone.utc)
    excluded = {"Factory", "localtime", "posixrules", "right/UTC", "UTC"}
    return sorted(
        (_metadata(name, now) for name in available_timezones() if name not in excluded and "/" in name),
        key=lambda item: (item["country"] or "ZZZ", item["id"]),
    )
