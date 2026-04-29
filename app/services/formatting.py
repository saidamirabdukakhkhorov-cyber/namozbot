from app.core.constants import PRAYER_NAMES
from app.services.i18n import prayer_label
def format_prayer_breakdown(language: str, breakdown: dict[str, int]) -> str:
    return "\n".join(f"{prayer_label(language, p)}: {breakdown.get(p, 0)}" for p in PRAYER_NAMES)
