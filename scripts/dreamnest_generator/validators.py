from typing import Any

from .categories import Category
from .config import Settings
from .text_utils import joined_page_text, normalized_title, total_non_space_chars, total_words

CJK_LANGUAGES = {"zh-Hans", "ja", "ko"}


def validate_pages(
    pages: Any,
    *,
    min_count: int,
    max_count: int,
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(pages, list):
        raise RuntimeError("Story pages must be an array")

    page_count = len(pages)
    if expected_count is not None and page_count != expected_count:
        raise RuntimeError(f"Translated pages must contain exactly {expected_count} pages to match the source story")

    if expected_count is None and not (min_count <= page_count <= max_count):
        raise RuntimeError(f"Story pages must contain between {min_count} and {max_count} pages, got {page_count}")

    normalized = []
    for index, raw_page in enumerate(pages, start=1):
        if not isinstance(raw_page, dict):
            raise RuntimeError(f"Page {index} must be an object")

        text = str(raw_page.get("text", "")).strip()
        if not text:
            raise RuntimeError(f"Page {index} text is empty")

        normalized.append(
            {
                # Reindex defensively so generated duplicate/missing indexes do not break image mapping.
                "index": index,
                "text": text,
                "image_prompt": raw_page.get("image_prompt"),
            }
        )

    return normalized


def validate_zh_story_style(story: dict[str, Any], category: Category) -> None:
    text = joined_page_text(story["pages"])
    hard_banned = [
        "这将是",
        "星光铺成的被子",
        "最深的睡前真理",
        "共同的呼吸",
        "用双手和心灵",
        "最后一个画面",
        "这个画面",
        "画面是",
        "镜头",
        "插画",
        "场景",
    ]
    soft_banned = [
        "不是",
        "而是",
        "温柔",
        "善意",
        "心灵",
        "光芒",
        "低语",
        "编织",
        "梦想",
        "呼吸",
    ]

    for phrase in hard_banned:
        if phrase in text:
            raise RuntimeError(f"Generated Chinese story contains AI-flavored phrase: {phrase}")

    soft_hits = sum(text.count(phrase) for phrase in soft_banned)
    if soft_hits > 12:
        raise RuntimeError(f"Generated Chinese story has too many abstract/AI-flavored phrases: {soft_hits}")

    category_mentions = text.count(category["zh"])
    if category_mentions > 4:
        raise RuntimeError(f"Generated Chinese story repeats category name too often: {category_mentions}")


def validate_story_title(title: str, category: Category, language_code: str) -> None:
    normalized = normalized_title(title)
    forbidden_values = {
        category["slug"],
        category["en"],
        category["zh"],
        category["en"].replace(" ", ""),
    }
    forbidden = {normalized_title(value) for value in forbidden_values if value}

    if normalized in forbidden or len(normalized) < 6:
        raise RuntimeError(
            f"Generated {language_code} title is not story-specific: {title!r} for category {category['slug']}"
        )


def validate_canonical_story(story: dict[str, Any], category: Category, settings: Settings) -> dict[str, Any]:
    required_keys = ["title", "intro", "pages", "cover_prompt", "hero_prompt", "category_slug"]
    for key in required_keys:
        if key not in story:
            raise RuntimeError(f"Generated story is missing key: {key}")

    if story["category_slug"] != category["slug"]:
        raise RuntimeError(f"Generated category_slug mismatch: {story['category_slug']} != {category['slug']}")

    validate_story_title(str(story["title"]), category, settings.source_language)
    story["pages"] = validate_pages(
        story["pages"],
        min_count=settings.min_page_count,
        max_count=settings.max_page_count,
    )

    if settings.source_language in CJK_LANGUAGES:
        char_count = total_non_space_chars(story["pages"])
        if char_count < settings.min_source_cjk_chars:
            raise RuntimeError(
                f"Generated {settings.source_language} story too short: {char_count} < {settings.min_source_cjk_chars} non-space chars"
            )
        if settings.source_language == "zh-Hans":
            validate_zh_story_style(story, category)
    else:
        words = total_words(story["pages"])
        if words < settings.min_source_words:
            raise RuntimeError(f"Generated {settings.source_language} story too short: {words} < {settings.min_source_words} words")

    return story


def validate_translated_story(
    translated: dict[str, Any],
    category: Category,
    target_language: str,
    settings: Settings,
    expected_page_count: int,
) -> dict[str, Any]:
    validate_story_title(str(translated.get("title", "")), category, target_language)
    translated["pages"] = validate_pages(
        translated.get("pages"),
        min_count=settings.min_page_count,
        max_count=settings.max_page_count,
        expected_count=expected_page_count,
    )
    translated["language_code"] = target_language

    if target_language in CJK_LANGUAGES:
        char_count = total_non_space_chars(translated["pages"])
        if char_count < settings.min_translated_cjk_chars:
            raise RuntimeError(
                f"Translated {target_language} story too short: {char_count} < {settings.min_translated_cjk_chars} non-space chars"
            )
    elif target_language == "en":
        words = total_words(translated["pages"])
        if words < settings.min_source_words:
            raise RuntimeError(f"Translated English story too short: {words} < {settings.min_source_words} words")

    return translated
