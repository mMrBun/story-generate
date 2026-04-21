import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from supabase import create_client

from .categories import CATEGORIES, Category, category_name_for_language
from .config import Settings, story_slug
from .openai_api import generate_canonical_story, generate_image_bytes, translate_story
from .repository import ensure_category_rows, insert_story_translation, story_exists, upload_image
from .story_builder import normalize_pages, pages_for_legacy_story
from .text_utils import total_non_space_chars, total_words


def wait_between_categories(settings: Settings, category_index: int, total_categories: int) -> None:
    if category_index >= total_categories or settings.batch_category_delay_seconds <= 0:
        return
    print(f"Waiting {settings.batch_category_delay_seconds:g}s before next category batch...")
    time.sleep(settings.batch_category_delay_seconds)


def generate_story_with_retries(openai_client: OpenAI, category: Category, slug: str, settings: Settings) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, settings.story_generation_retries + 1):
        try:
            return generate_canonical_story(openai_client, category, slug, settings)
        except Exception as exc:
            last_error = exc
            print(
                f"Story generation attempt {attempt}/{settings.story_generation_retries} failed for {slug}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(f"Failed to generate valid canonical story for {slug}") from last_error


def translate_story_with_retries(
    openai_client: OpenAI,
    story: dict[str, Any],
    language_code: str,
    category: Category,
    settings: Settings,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, settings.translation_retries + 1):
        try:
            return translate_story(openai_client, story, language_code, category, settings)
        except Exception as exc:
            last_error = exc
            print(
                f"Translation attempt {attempt}/{settings.translation_retries} failed for {story['slug']} -> {language_code}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError(f"Failed to translate story {story['slug']} to {language_code}") from last_error


def generate_images_for_story(
    openai_client: OpenAI,
    supabase,
    bucket: str,
    slug: str,
    canonical_story: dict[str, Any],
    settings: Settings,
) -> tuple[str, str, dict[int, str]]:
    base_path = f"stories/{slug}"
    cover_path = f"{base_path}/cover.{settings.image_format}"
    hero_path = f"{base_path}/hero.{settings.image_format}"

    print(f"Generating cover image for {slug}...")
    cover_bytes = generate_image_bytes(openai_client, canonical_story["cover_prompt"], settings)
    upload_image(supabase, bucket, cover_path, cover_bytes, settings)

    print(f"Generating hero image for {slug}...")
    hero_bytes = generate_image_bytes(openai_client, canonical_story["hero_prompt"], settings)
    upload_image(supabase, bucket, hero_path, hero_bytes, settings)

    page_image_paths: dict[int, str] = {}
    if settings.generate_page_images:
        for raw_page in canonical_story["pages"]:
            page_index = int(raw_page["index"])
            page_prompt = raw_page.get("image_prompt")
            if not page_prompt:
                raise RuntimeError(f"Page {page_index} is missing image_prompt")

            page_path = f"{base_path}/page-{page_index}.{settings.image_format}"
            print(f"Generating page {page_index} image for {slug}...")
            page_bytes = generate_image_bytes(openai_client, page_prompt, settings)
            upload_image(supabase, bucket, page_path, page_bytes, settings)
            page_image_paths[page_index] = page_path
    else:
        page_image_paths[1] = hero_path

    return cover_path, hero_path, page_image_paths


def generate_and_insert_category_story(
    openai_client: OpenAI,
    supabase,
    bucket: str,
    category: Category,
    settings: Settings,
    skip_existing_slug: bool,
    unique_slug: bool,
) -> bool:
    slug = story_slug(category["slug"], settings, unique_run=unique_slug)

    if skip_existing_slug and story_exists(supabase, slug):
        print(f"Story already exists: {slug}")
        return False

    print(f"Generating canonical {settings.source_language} story for category: {category['en']} ({category['slug']})")
    canonical_story = generate_story_with_retries(openai_client, category, slug, settings)

    translations = {
        settings.source_language: translate_story(openai_client, canonical_story, settings.source_language, category, settings)
    }
    for language_code in settings.target_languages:
        if language_code == settings.source_language:
            continue
        translations[language_code] = translate_story_with_retries(openai_client, canonical_story, language_code, category, settings)

    cover_path, hero_path, page_image_paths = generate_images_for_story(
        openai_client,
        supabase,
        bucket,
        slug,
        canonical_story,
        settings,
    )
    canonical_pages = normalize_pages(canonical_story["pages"], page_image_paths)
    legacy_language = settings.legacy_stories_language if settings.legacy_stories_language in translations else settings.source_language
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
                "source_model": settings.text_model,
                "image_model": settings.image_model,
                "generation_prompt": f"canonical {settings.source_language} story generation, then translation; category={category['slug']}; target_languages={','.join(translations.keys())}",
                "is_published": settings.publish_immediately,
                "published_at": datetime.now(timezone.utc).isoformat() if settings.publish_immediately else None,
            }
        )
        .execute()
    )

    for translated_story in translations.values():
        insert_story_translation(supabase, slug, translated_story, canonical_pages)

    source_words = total_words(canonical_story["pages"])
    source_chars = total_non_space_chars(canonical_story["pages"])
    print(f"Generated story: {canonical_story['title']}")
    print(f"Slug: {slug}")
    print(f"Category: {category['en']} / {category['slug']}")
    print(f"Source language: {settings.source_language}")
    if settings.source_language in {"zh-Hans", "ja", "ko"}:
        print(f"Source chars: {source_chars}")
    else:
        print(f"Source words: {source_words}")
    for language_code, translated_story in translations.items():
        if language_code in {"zh-Hans", "ja", "ko"}:
            print(f"{language_code} chars: {total_non_space_chars(translated_story['pages'])}")
    print(f"Inserted rows: {len(insert_result.data or [])}")
    print(f"Images uploaded under: stories/{slug}")
    return True


def categories_for_run(settings: Settings) -> tuple[list[Category], bool, bool]:
    if settings.generate_all_categories:
        categories = CATEGORIES
        if settings.max_categories_per_run > 0:
            categories = categories[:settings.max_categories_per_run]
        print(f"Generation mode: all categories ({len(categories)} categories this run)")
        return categories, False, True

    category = random.choice(CATEGORIES)
    print(f"Generation mode: one random category ({category['slug']})")
    return [category], True, False


def main() -> None:
    settings = Settings()

    if not settings.generation_enabled:
        print("Story generation disabled by STORY_GENERATION_ENABLED=false. Exiting without changes.")
        return

    settings.require_env()

    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]

    try:
        ensure_category_rows(supabase)
    except Exception as exc:
        print(f"Warning: failed to ensure category rows: {exc}", file=sys.stderr)

    generated_count = 0
    skipped_count = 0
    failed_count = 0
    categories_to_generate, skip_existing_slug, unique_slug = categories_for_run(settings)

    for index, category in enumerate(categories_to_generate, start=1):
        should_continue = True
        try:
            did_generate = generate_and_insert_category_story(
                openai_client,
                supabase,
                bucket,
                category,
                settings,
                skip_existing_slug=skip_existing_slug,
                unique_slug=unique_slug,
            )
            if did_generate:
                generated_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            failed_count += 1
            print(f"Failed category {category['slug']}: {exc}", file=sys.stderr)
            should_continue = settings.generate_all_categories and settings.continue_on_category_failure
            if not should_continue:
                raise
        if should_continue:
            wait_between_categories(settings, index, len(categories_to_generate))

    print("Daily generation complete")
    print(f"Generated: {generated_count}")
    print(f"Skipped existing: {skipped_count}")
    print(f"Failed: {failed_count}")
