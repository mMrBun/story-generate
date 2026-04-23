import os
from dataclasses import dataclass, field
from typing import Sequence

from dotenv import load_dotenv


load_dotenv()

REQUIRED_ENV = (
    "MXNZP_APP_ID",
    "MXNZP_APP_SECRET",
    "DEEPLX_URL",
    "DEEPLX_TOKEN",
    "OPENAI_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_STORAGE_BUCKET",
)


def env_bool(key: str, default: bool) -> bool:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(key: str, default: int) -> int:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        return default
    return int(raw_value)


def env_list(key: str, default: str) -> list[str]:
    raw_value = os.getenv(key)
    if raw_value is None or raw_value.strip() == "":
        raw_value = default
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # Public workflow controls. Keep this small on purpose.
    generation_enabled: bool = field(default_factory=lambda: env_bool("STORY_GENERATION_ENABLED", True))
    stories_per_category_per_run: int = field(default_factory=lambda: env_int("STORIES_PER_CATEGORY_PER_RUN", 3))

    # Connection and secret configuration.
    mxnzp_base_url: str = field(default_factory=lambda: os.getenv("MXNZP_BASE_URL", "https://www.mxnzp.com/api/story"))
    mxnzp_app_id: str = field(default_factory=lambda: os.getenv("MXNZP_APP_ID", ""))
    mxnzp_app_secret: str = field(default_factory=lambda: os.getenv("MXNZP_APP_SECRET", ""))

    deeplx_url: str = field(default_factory=lambda: os.getenv("DEEPLX_URL", ""))
    deeplx_urls: list[str] = field(default_factory=lambda: env_list("DEEPLX_URLS", os.getenv("DEEPLX_URL", "")))
    deeplx_token: str = field(default_factory=lambda: os.getenv("DEEPLX_TOKEN", ""))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    cloudflare_account_id: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_ACCOUNT_ID", ""))
    cloudflare_api_token: str = field(default_factory=lambda: os.getenv("CLOUDFLARE_API_TOKEN", ""))

    # Fixed product defaults. Change these in code when product requirements change.
    story_api_request_delay_seconds: float = 1.1
    excluded_story_type_names: list[str] = field(default_factory=lambda: ["童话作文"])
    target_languages: list[str] = field(default_factory=lambda: ["zh-Hans", "en", "ja", "ko"])

    deeplx_request_delay_seconds: float = 2.0
    deeplx_max_retries: int = 5
    deeplx_retry_delay_seconds: float = 5.0
    deeplx_error_cooldown_seconds: float = 30.0
    deeplx_max_chars_per_request: int = 1200

    openai_text_model: str = "gpt-5-mini"
    openai_request_delay_seconds: float = 1.0

    flux_model: str = "@cf/black-forest-labs/flux-1-schnell"
    flux_steps: int = 8
    flux_request_delay_seconds: float = 2.0
    card_image_width: int = 1008
    card_image_height: int = 1008
    hero_image_width: int = 752
    hero_image_height: int = 1328
    image_format: str = "png"


    def require_env(self, required_keys: Sequence[str] = REQUIRED_ENV) -> None:
        missing = [key for key in required_keys if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing required env: {', '.join(missing)}")

    @property
    def cloudflare_flux_url(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.cloudflare_account_id}/ai/run/{self.flux_model}"
