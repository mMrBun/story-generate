import base64
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client


load_dotenv()


REQUIRED_ENV = [
    "OPENAI_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_STORAGE_BUCKET",
]

TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5-nano")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
IMAGE_SIZE = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")
IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "low")
IMAGE_FORMAT = os.getenv("OPENAI_IMAGE_FORMAT", "webp")
RUN_SLUG_SUFFIX = datetime.now(timezone.utc).strftime("%H%M%S")
PAGE_COUNT = int(os.getenv("STORY_PAGE_COUNT", "8"))
MIN_SOURCE_WORDS = int(os.getenv("STORY_MIN_SOURCE_WORDS", "900"))
MIN_TRANSLATED_CJK_CHARS = int(os.getenv("STORY_MIN_TRANSLATED_CJK_CHARS", "1200"))
LEGACY_STORIES_LANGUAGE = os.getenv("LEGACY_STORIES_LANGUAGE", "zh-Hans").strip()
STORY_GENERATION_RETRIES = int(os.getenv("STORY_GENERATION_RETRIES", "3"))
TRANSLATION_RETRIES = int(os.getenv("STORY_TRANSLATION_RETRIES", "3"))
PUBLISH_IMMEDIATELY = os.getenv("PUBLISH_IMMEDIATELY", "false").lower() == "true"
GENERATE_ALL_CATEGORIES = os.getenv("GENERATE_ALL_CATEGORIES", "false").lower() == "true"
GENERATE_PAGE_IMAGES = os.getenv("GENERATE_PAGE_IMAGES", "true").lower() == "true"
TARGET_LANGUAGES = [
    language.strip()
    for language in os.getenv("TARGET_LANGUAGES", "zh-Hans").split(",")
    if language.strip()
]

CATEGORIES = [
    {"slug": "fairy_tale", "zh": "童话", "en": "Fairy Tales", "value_en": "imagination, wonder, and gentle magical encounters"},
    {"slug": "prophecy", "zh": "预言", "en": "Prophecy", "value_en": "gentle foresight, wise choices, interpreting signs, and learning that the future can be shaped by kindness"},
    {"slug": "perseverance", "zh": "恒心", "en": "Perseverance", "value_en": "patience, persistence, and steady long-term effort"},
    {"slug": "wit", "zh": "机智", "en": "Wit", "value_en": "clever problem solving without tricking or hurting others"},
    {"slug": "unity", "zh": "团结", "en": "Unity", "value_en": "cooperation, helping each other, and reaching a goal together"},
    {"slug": "reflection", "zh": "反省", "en": "Reflection", "value_en": "understanding mistakes, noticing feelings, and gently making things right"},
    {"slug": "sharing", "zh": "分享", "en": "Sharing", "value_en": "generosity, shared joy, and caring for others"},
    {"slug": "diligence", "zh": "勤奋", "en": "Diligence", "value_en": "careful practice, steady work, and doing small things well"},
    {"slug": "courage", "zh": "勇气", "en": "Courage", "value_en": "trying bravely, speaking honestly, and facing small difficulties"},
    {"slug": "warmth", "zh": "温馨", "en": "Warmth", "value_en": "family, companionship, comfort, and emotional warmth"},
    {"slug": "respect", "zh": "尊重", "en": "Respect", "value_en": "respecting differences, boundaries, elders, friends, and nature"},
    {"slug": "confidence", "zh": "自信", "en": "Confidence", "value_en": "believing in oneself, self-acceptance, and gentle growth"},
    {"slug": "cherish", "zh": "珍惜", "en": "Cherish", "value_en": "cherishing time, friendship, nature, and what one already has"},
]

LANGUAGE_PROFILES: dict[str, dict[str, str]] = {
    "en": {
        "name": "English",
        "length_rule": f"The total story body must be at least {MIN_SOURCE_WORDS} English words.",
        "style_rule": "Use warm, polished, natural children's bedtime-story English.",
    },
    "zh-Hans": {
        "name": "Simplified Chinese",
        "length_rule": f"The translated story body must be at least {MIN_TRANSLATED_CJK_CHARS} Chinese characters, excluding punctuation and whitespace.",
        "style_rule": "Use natural Simplified Chinese for children. Do not sound machine-translated. Keep the story long and complete; do not summarize.",
    },
    "ja": {
        "name": "Japanese",
        "length_rule": f"The translated story body must be at least {MIN_TRANSLATED_CJK_CHARS} Japanese characters, excluding punctuation and whitespace.",
        "style_rule": "Use natural Japanese for children. Keep a gentle bedtime tone. Do not summarize.",
    },
    "ko": {
        "name": "Korean",
        "length_rule": f"The translated story body must be at least {MIN_TRANSLATED_CJK_CHARS} Korean characters, excluding punctuation and whitespace.",
        "style_rule": "Use natural Korean for children. Keep a gentle bedtime tone. Do not summarize.",
    },
}


def require_env() -> None:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")


def today_slug_prefix() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"daily-story-{today}"


def run_slug_suffix() -> str:
    return RUN_SLUG_SUFFIX


def story_slug(category_slug: str, unique_run: bool = False) -> str:
    base_slug = f"{today_slug_prefix()}-{category_slug}"
    if unique_run:
        return f"{base_slug}-{run_slug_suffix()}"
    return base_slug


def safe_json_loads(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON: {content}") from exc


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def total_words(pages: list[dict[str, Any]]) -> int:
    return sum(word_count(str(page.get("text", ""))) for page in pages)


def cjk_char_count(text: str) -> int:
    return len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))


def total_cjk_chars(pages: list[dict[str, Any]]) -> int:
    return sum(cjk_char_count(str(page.get("text", ""))) for page in pages)


def non_space_char_count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def total_non_space_chars(pages: list[dict[str, Any]]) -> int:
    return sum(non_space_char_count(str(page.get("text", ""))) for page in pages)


def story_text_for_prompt(story: dict[str, Any]) -> str:
    page_text = "\n".join(
        f"Page {page['index']}: {page['text']}"
        for page in story["pages"]
    )
    return f"Title: {story['title']}\nIntro: {story.get('intro', '')}\n{page_text}"


def validate_pages(pages: Any, expected_count: int) -> list[dict[str, Any]]:
    if not isinstance(pages, list) or len(pages) != expected_count:
        raise RuntimeError(f"Story pages must contain exactly {expected_count} pages")

    normalized = []
    for index, raw_page in enumerate(pages, start=1):
        if not isinstance(raw_page, dict):
            raise RuntimeError(f"Page {index} must be an object")
        normalized.append(
            {
                "index": int(raw_page.get("index", index)),
                "text": str(raw_page.get("text", "")).strip(),
                "image_prompt": raw_page.get("image_prompt"),
            }
        )

    normalized.sort(key=lambda page: page["index"])
    return normalized


def generate_canonical_story(client: OpenAI, category: dict[str, str], slug: str) -> dict[str, Any]:
    prompt = f"""
You are a children's bedtime story writer for an app called DreamNest.

Generate one original long-form bedtime story in English.

Category:
- slug: {category['slug']}
- English name: {category['en']}
- Meaning: {category['value_en']}

Return valid JSON only. No markdown. No extra commentary.

JSON schema:
{{
  "slug": "{slug}",
  "category_slug": "{category['slug']}",
  "language_code": "en",
  "title": string,
  "intro": string,
  "duration_minutes": number,
  "cover_prompt": string,
  "hero_prompt": string,
  "pages": [
    {{
      "index": number,
      "text": string,
      "image_prompt": string
    }}
  ]
}}

Hard requirements:
- The story body must be at least {MIN_SOURCE_WORDS} English words in total.
- Split the story into exactly {PAGE_COUNT} pages.
- Each page should be a complete, substantial paragraph.
- category_slug must be exactly "{category['slug']}".
- slug must be exactly "{slug}".
- The story must be calm, warm, imaginative, and suitable before sleep.
- The category value should emerge naturally through the plot, not as a lecture.
- Avoid violence, horror, death, weapons, punishment, shame, or intense conflict.
- Do not reference or imitate existing copyrighted characters, franchises, or famous fairy tales.
- cover_prompt, hero_prompt, and image_prompt must be in English.
- Image prompts should describe cozy children's-book illustrations with no text, no watermark, and no UI.
""".strip()

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You output strict JSON for an automated bedtime-story publishing pipeline.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI returned empty story content")

    story = safe_json_loads(content)
    required_keys = ["title", "intro", "pages", "cover_prompt", "hero_prompt", "category_slug"]
    for key in required_keys:
        if key not in story:
            raise RuntimeError(f"Generated story is missing key: {key}")

    if story["category_slug"] != category["slug"]:
        raise RuntimeError(f"Generated category_slug mismatch: {story['category_slug']} != {category['slug']}")

    story["pages"] = validate_pages(story["pages"], PAGE_COUNT)
    words = total_words(story["pages"])
    if words < MIN_SOURCE_WORDS:
        raise RuntimeError(f"Generated English story too short: {words} < {MIN_SOURCE_WORDS} words")

    story["slug"] = slug
    story["category_slug"] = category["slug"]
    story["language_code"] = "en"
    return story


def translate_story(client: OpenAI, canonical_story: dict[str, Any], target_language: str) -> dict[str, Any]:
    if target_language == "en":
        return {
            "language_code": "en",
            "title": canonical_story["title"],
            "intro": canonical_story.get("intro"),
            "pages": [
                {
                    "index": page["index"],
                    "text": page["text"],
                    "image_prompt": page.get("image_prompt"),
                }
                for page in canonical_story["pages"]
            ],
        }

    profile = LANGUAGE_PROFILES.get(target_language)
    if not profile:
        raise RuntimeError(f"Unsupported target language: {target_language}")

    prompt = f"""
Translate the following DreamNest bedtime story into {profile['name']}.

Return valid JSON only. No markdown. No extra commentary.

Target language code: {target_language}

JSON schema:
{{
  "language_code": "{target_language}",
  "title": string,
  "intro": string,
  "pages": [
    {{
      "index": number,
      "text": string
    }}
  ]
}}

Translation requirements:
- Preserve the plot, page count, page order, emotional tone, and bedtime pacing.
- Translate title, intro, and every page text.
- Do not translate image prompts; image prompts are stored separately from the English canonical story.
- Do not summarize, shorten, omit scenes, or add new plot events.
- {profile['length_rule']}
- {profile['style_rule']}

Source story:
{story_text_for_prompt(canonical_story)}
""".strip()

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You translate structured bedtime stories and return strict JSON only.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"OpenAI returned empty translation content for {target_language}")

    translated = safe_json_loads(content)
    translated["pages"] = validate_pages(translated.get("pages"), PAGE_COUNT)
    translated["language_code"] = target_language

    if target_language in {"zh-Hans", "ja", "ko"}:
        char_count = total_non_space_chars(translated["pages"])
        if char_count < MIN_TRANSLATED_CJK_CHARS:
            raise RuntimeError(
                f"Translated {target_language} story too short: {char_count} < {MIN_TRANSLATED_CJK_CHARS} non-space chars"
            )

    return translated


def build_image_prompt(prompt: str) -> str:
    return f"""
Create a cozy illustrated bedtime story image.

Style:
- dreamy children's book illustration
- soft moonlit lighting
- gentle colors
- magical but calm atmosphere
- warm, safe, soothing composition
- no scary elements
- no text, no watermark, no UI

Scene:
{prompt}
""".strip()


def generate_image_bytes(client: OpenAI, prompt: str) -> bytes:
    response = client.images.generate(
        model=IMAGE_MODEL,
        prompt=build_image_prompt(prompt),
        size=IMAGE_SIZE,
        quality=IMAGE_QUALITY,
        output_format=IMAGE_FORMAT,
        n=1,
    )

    if not response.data:
        raise RuntimeError("OpenAI image generation returned no data")

    image_base64 = response.data[0].b64_json
    if not image_base64:
        raise RuntimeError("OpenAI image generation returned empty b64_json")

    return base64.b64decode(image_base64)


def upload_image(supabase, bucket: str, storage_path: str, image_bytes: bytes) -> str:
    content_type = f"image/{IMAGE_FORMAT}"

    supabase.storage.from_(bucket).upload(
        path=storage_path,
        file=image_bytes,
        file_options={
            "content-type": content_type,
            "cache-control": "31536000",
            "upsert": "true",
        },
    )

    return storage_path


def pages_for_legacy_story(
    translated_story: dict[str, Any],
    canonical_pages_with_images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    image_lookup = {int(page["index"]): page for page in canonical_pages_with_images}
    pages = []

    for translated_page in translated_story["pages"]:
        page_index = int(translated_page["index"])
        image_payload = image_lookup[page_index]
        pages.append(
            {
                "index": page_index,
                "text": translated_page["text"],
                "image_path": image_payload["image_path"],
                "image_prompt": image_payload.get("image_prompt"),
            }
        )

    pages.sort(key=lambda page: page["index"])
    return pages


def category_name_for_language(category: dict[str, str], language_code: str) -> str:
    if language_code == "zh-Hans":
        return category["zh"]
    return category["en"]


def normalize_pages(story_pages: list[dict[str, Any]], page_image_paths: dict[int, str]) -> list[dict[str, Any]]:
    pages = []
    fallback_image_path = next(iter(page_image_paths.values()), None)

    for raw_page in story_pages:
        page_index = int(raw_page["index"])
        image_path = page_image_paths.get(page_index) or fallback_image_path
        if not image_path:
            raise RuntimeError(f"Page {page_index} has no image path")

        pages.append(
            {
                "index": page_index,
                "text": raw_page["text"],
                "image_path": image_path,
                "image_prompt": raw_page.get("image_prompt"),
            }
        )

    pages.sort(key=lambda page: page["index"])
    return pages


def story_exists(supabase, slug: str) -> bool:
    existing = supabase.table("stories").select("id").eq("slug", slug).limit(1).execute()
    return bool(existing.data)


def ensure_category_rows(supabase) -> None:
    for sort_order, category in enumerate(CATEGORIES, start=1):
        supabase.table("story_categories").upsert(
            {
                "slug": category["slug"],
                "sort_order": sort_order * 10,
            },
            on_conflict="slug",
        ).execute()

        for language_code, name in [("zh-Hans", category["zh"]), ("en", category["en"] )]:
            supabase.table("story_category_translations").upsert(
                {
                    "category_slug": category["slug"],
                    "language_code": language_code,
                    "name": name,
                },
                on_conflict="category_slug,language_code",
            ).execute()


def insert_story_translation(
    supabase,
    slug: str,
    translated_story: dict[str, Any],
    pages_with_images: list[dict[str, Any]],
) -> None:
    try:
        language_code = translated_story["language_code"]
        pages = []
        page_lookup = {int(page["index"]): page for page in pages_with_images}

        for page in translated_story["pages"]:
            page_index = int(page["index"])
            image_payload = page_lookup[page_index]
            pages.append(
                {
                    "index": page_index,
                    "text": page["text"],
                    "image_path": image_payload["image_path"],
                    "image_prompt": image_payload.get("image_prompt"),
                }
            )

        supabase.table("story_translations").upsert(
            {
                "story_slug": slug,
                "language_code": language_code,
                "title": translated_story["title"],
                "intro": translated_story.get("intro"),
                "tag_line": translated_story.get("intro"),
                "pages": pages,
            },
            on_conflict="story_slug,language_code",
        ).execute()
    except Exception as exc:
        print(f"Warning: failed to upsert story_translations for {slug}: {exc}", file=sys.stderr)


def generate_story_with_retries(openai_client: OpenAI, category: dict[str, str], slug: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, STORY_GENERATION_RETRIES + 1):
        try:
            return generate_canonical_story(openai_client, category, slug)
        except Exception as exc:
            last_error = exc
            print(
                f"Story generation attempt {attempt}/{STORY_GENERATION_RETRIES} failed for {slug}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(f"Failed to generate valid canonical story for {slug}") from last_error


def translate_story_with_retries(openai_client: OpenAI, story: dict[str, Any], language_code: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, TRANSLATION_RETRIES + 1):
        try:
            return translate_story(openai_client, story, language_code)
        except Exception as exc:
            last_error = exc
            print(
                f"Translation attempt {attempt}/{TRANSLATION_RETRIES} failed for {story['slug']} -> {language_code}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(f"Failed to translate story {story['slug']} to {language_code}") from last_error


def generate_and_insert_category_story(
    openai_client: OpenAI,
    supabase,
    bucket: str,
    category: dict[str, str],
    skip_existing_slug: bool,
    unique_slug: bool,
) -> bool:
    slug = story_slug(category["slug"], unique_run=unique_slug)

    if skip_existing_slug and story_exists(supabase, slug):
        print(f"Story already exists: {slug}")
        return False

    print(f"Generating canonical English story for category: {category['en']} ({category['slug']})")
    canonical_story = generate_story_with_retries(openai_client, category, slug)

    translations = {"en": translate_story(openai_client, canonical_story, "en")}
    for language_code in TARGET_LANGUAGES:
        if language_code == "en":
            continue
        translations[language_code] = translate_story_with_retries(openai_client, canonical_story, language_code)

    base_path = f"stories/{slug}"
    cover_path = f"{base_path}/cover.{IMAGE_FORMAT}"
    hero_path = f"{base_path}/hero.{IMAGE_FORMAT}"

    print(f"Generating cover image for {slug}...")
    cover_bytes = generate_image_bytes(openai_client, canonical_story["cover_prompt"])
    upload_image(supabase, bucket, cover_path, cover_bytes)

    print(f"Generating hero image for {slug}...")
    hero_bytes = generate_image_bytes(openai_client, canonical_story["hero_prompt"])
    upload_image(supabase, bucket, hero_path, hero_bytes)

    page_image_paths: dict[int, str] = {}

    if GENERATE_PAGE_IMAGES:
        for raw_page in canonical_story["pages"]:
            page_index = int(raw_page["index"])
            page_prompt = raw_page.get("image_prompt")

            if not page_prompt:
                raise RuntimeError(f"Page {page_index} is missing image_prompt")

            page_path = f"{base_path}/page-{page_index}.{IMAGE_FORMAT}"

            print(f"Generating page {page_index} image for {slug}...")
            page_bytes = generate_image_bytes(openai_client, page_prompt)
            upload_image(supabase, bucket, page_path, page_bytes)

            page_image_paths[page_index] = page_path
    else:
        page_image_paths[1] = hero_path

    canonical_pages = normalize_pages(canonical_story["pages"], page_image_paths)
    legacy_language = LEGACY_STORIES_LANGUAGE if LEGACY_STORIES_LANGUAGE in translations else "en"
    legacy_story = translations[legacy_language]
    legacy_pages = pages_for_legacy_story(legacy_story, canonical_pages)

    insert_result = (
        supabase.table("stories")
        .insert(
            {
                "slug": slug,
                "title": legacy_story["title"],
                "intro": legacy_story.get("intro"),
                "tag": category_name_for_language(category, legacy_language),
                "category_slug": category["slug"],
                "content_language": legacy_language,
                "duration_minutes": canonical_story.get("duration_minutes", 12),
                "cover_image_path": cover_path,
                "thumbnail_image_path": cover_path,
                "hero_image_path": hero_path,
                "pages": legacy_pages,
                "source_model": TEXT_MODEL,
                "image_model": IMAGE_MODEL,
                "generation_prompt": f"canonical English story generation, then translation; category={category['slug']}; target_languages={','.join(translations.keys())}",
                "is_published": PUBLISH_IMMEDIATELY,
                "published_at": datetime.now(timezone.utc).isoformat() if PUBLISH_IMMEDIATELY else None,
            }
        )
        .execute()
    )

    for translated_story in translations.values():
        insert_story_translation(supabase, slug, translated_story, canonical_pages)

    source_words = total_words(canonical_story["pages"])
    print(f"Generated story: {canonical_story['title']}")
    print(f"Slug: {slug}")
    print(f"Category: {category['en']} / {category['slug']}")
    print(f"English source words: {source_words}")
    for language_code, translated_story in translations.items():
        if language_code in {"zh-Hans", "ja", "ko"}:
            print(f"{language_code} chars: {total_non_space_chars(translated_story['pages'])}")
    print(f"Inserted rows: {len(insert_result.data or [])}")
    print(f"Images uploaded under: {base_path}")
    return True


def main() -> None:
    require_env()

    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]

    try:
        ensure_category_rows(supabase)
    except Exception as exc:
        print(f"Warning: failed to ensure category rows: {exc}", file=sys.stderr)

    generated_count = 0
    skipped_count = 0

    if GENERATE_ALL_CATEGORIES:
        categories_to_generate = CATEGORIES
        skip_existing_slug = False
        unique_slug = True
        print("Generation mode: all categories")
    else:
        categories_to_generate = [random.choice(CATEGORIES)]
        skip_existing_slug = True
        unique_slug = False
        print(f"Generation mode: one random category ({categories_to_generate[0]['slug']})")

    for category in categories_to_generate:
        try:
            did_generate = generate_and_insert_category_story(
                openai_client,
                supabase,
                bucket,
                category,
                skip_existing_slug=skip_existing_slug,
                unique_slug=unique_slug,
            )
            if did_generate:
                generated_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            print(f"Failed category {category['slug']}: {exc}", file=sys.stderr)
            raise

    print("Daily generation complete")
    print(f"Generated: {generated_count}")
    print(f"Skipped existing: {skipped_count}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to generate daily stories: {exc}", file=sys.stderr)
        raise
