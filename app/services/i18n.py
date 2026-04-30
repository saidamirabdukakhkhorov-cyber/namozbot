import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from app.core.constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
@lru_cache(maxsize=1)
def load_locales():
    return {lang: json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8")) for lang in SUPPORTED_LANGUAGES}
def t(lang_code: str | None, key: str, **kwargs: Any) -> str:
    lang = lang_code if lang_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    template = load_locales().get(lang, {}).get(key) or load_locales().get(DEFAULT_LANGUAGE, {}).get(key) or key
    try: return template.format(**kwargs)
    except Exception: return template
def prayer_label(language: str | None, prayer_name: str) -> str: return t(language, f"prayer.{prayer_name}")
