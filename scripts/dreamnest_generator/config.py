import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from dotenv import load_dotenv


load_dotenv()

REQUIRED_ENV = (
    "OPENAI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_STORAGE_BUCKET",
)


def env_bool(key: str, default: bool) -> bool:
    raw_value = os.getenv(key)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(key: str, default: int) -> int:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def env_float(key: str, default: float) -> float:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return default
    return float(raw_value)


def env_list(key: str, default: str) -> list[str]:
    raw_value = os.getenv(key, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    generation_enabled: bool = field(default_factory=lambda: env_bool("STORY_GENERATION_ENABLED", True))
    text_model: str = field(default_factory=lambda: os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini"))
    image_model: str = field(default_factory=lambda: os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"))
    image_size: str = field(default_factory=lambda: os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"))
    image_quality: str = field(default_factory=lambda: os.getenv("OPENAI_IMAGE_QUALITY", "medium"))
    image_format: str = field(default_factory=lambda: os.getenv("OPENAI_IMAGE_FORMAT", "webp"))
    run_slug_suffix: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%H%M%S"))
    page_count: int = field(default_factory=lambda: env_int("STORY_PAGE_COUNT", 8))
    min_page_count: int = field(default_factory=lambda: env_int("STORY_MIN_PAGE_COUNT", 6))
    max_page_count: int = field(default_factory=lambda: env_int("STORY_MAX_PAGE_COUNT", 10))
    min_source_words: int = field(default_factory=lambda: env_int("STORY_MIN_SOURCE_WORDS", 900))
    min_source_cjk_chars: int = field(default_factory=lambda: env_int("STORY_MIN_SOURCE_CJK_CHARS", 1200))
    min_source_cjk_chars_per_page: int = field(default_factory=lambda: env_int("STORY_MIN_SOURCE_CJK_CHARS_PER_PAGE", 200))
    max_source_cjk_chars_per_page: int = field(default_factory=lambda: env_int("STORY_MAX_SOURCE_CJK_CHARS_PER_PAGE", 260))
    min_translated_cjk_chars: int = field(default_factory=lambda: env_int("STORY_MIN_TRANSLATED_CJK_CHARS", 1200))
    source_language: str = field(default_factory=lambda: os.getenv("STORY_SOURCE_LANGUAGE", "zh-Hans").strip())
    legacy_stories_language: str = field(default_factory=lambda: os.getenv("LEGACY_STORIES_LANGUAGE", "zh-Hans").strip())
    story_generation_retries: int = field(default_factory=lambda: env_int("STORY_GENERATION_RETRIES", 3))
    translation_retries: int = field(default_factory=lambda: env_int("STORY_TRANSLATION_RETRIES", 3))
    publish_immediately: bool = field(default_factory=lambda: env_bool("PUBLISH_IMMEDIATELY", False))
    generate_all_categories: bool = field(default_factory=lambda: env_bool("GENERATE_ALL_CATEGORIES", False))
    generate_page_images: bool = field(default_factory=lambda: env_bool("GENERATE_PAGE_IMAGES", True))
    target_languages: list[str] = field(default_factory=lambda: env_list("TARGET_LANGUAGES", "zh-Hans,en,ja,ko"))
    max_categories_per_run: int = field(default_factory=lambda: env_int("MAX_CATEGORIES_PER_RUN", 0))
    text_request_delay_seconds: float = field(default_factory=lambda: env_float("OPENAI_TEXT_REQUEST_DELAY_SECONDS", 2.0))
    image_request_delay_seconds: float = field(default_factory=lambda: env_float("OPENAI_IMAGE_REQUEST_DELAY_SECONDS", 12.0))
    batch_category_delay_seconds: float = field(default_factory=lambda: env_float("BATCH_CATEGORY_DELAY_SECONDS", 30.0))
    continue_on_category_failure: bool = field(default_factory=lambda: env_bool("CONTINUE_ON_CATEGORY_FAILURE", True))

    def require_env(self, required_keys: Sequence[str] = REQUIRED_ENV) -> None:
        missing = [key for key in required_keys if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing required env: {', '.join(missing)}")


def today_slug_prefix() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"daily-story-{today}"


def story_slug(category_slug: str, settings: Settings, unique_run: bool = False) -> str:
    base_slug = f"{today_slug_prefix()}-{category_slug}"
    if unique_run:
        return f"{base_slug}-{settings.run_slug_suffix}"
    return base_slug


def language_profiles(settings: Settings) -> dict[str, dict[str, str]]:
    return {
        "en": {
            "name": "English",
            "length_rule": f"The total story body must be at least {settings.min_source_words} English words.",
            "style_rule": "Use warm, polished, natural children's bedtime-story English.",
        },
        "zh-Hans": {
            "name": "Simplified Chinese",
            "length_rule": f"The story body must be at least {settings.min_translated_cjk_chars} Chinese characters, excluding punctuation and whitespace.",
            "style_rule": "Use natural Simplified Chinese for children. Do not sound machine-translated. Keep the story long and complete; do not summarize.",
        },
        "ja": {
            "name": "Japanese",
            "length_rule": f"The story body must be at least {settings.min_translated_cjk_chars} Japanese characters, excluding punctuation and whitespace.",
            "style_rule": "Use natural Japanese for children. Keep a gentle bedtime tone. Do not summarize.",
        },
        "ko": {
            "name": "Korean",
            "length_rule": f"The story body must be at least {settings.min_translated_cjk_chars} Korean characters, excluding punctuation and whitespace.",
            "style_rule": "Use natural Korean for children. Keep a gentle bedtime tone. Do not summarize.",
        },
    }
