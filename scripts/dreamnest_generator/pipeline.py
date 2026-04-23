import os
import sys

from supabase import create_client

from .config import Settings
from .flux_api import FluxImageGenerator
from .models import StoryDetail, StorySummary, StoryType
from .prompt_writer import ImagePromptWriter
from .repository import insert_story, load_category_translations, load_import_cursor, save_import_cursor, story_exists, sync_story_categories, upload_image
from .story_api import StoryAPIClient
from .translator import DeepLXTranslator


def translate_category_names(
    translator: DeepLXTranslator,
    story_types: list[StoryType],
    target_languages: list[str],
    existing_translations: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    translations: dict[str, dict[str, str]] = {}
    existing_translations = existing_translations or {}

    for story_type in story_types:
        payload = dict(existing_translations.get(story_type.slug, {}))
        payload["zh-Hans"] = payload.get("zh-Hans") or story_type.name

        for language_code in target_languages:
            if language_code == "zh-Hans" or payload.get(language_code):
                continue
            try:
                payload[language_code] = translator.translate(story_type.name, "zh-Hans", language_code)
            except Exception as exc:
                print(f"Warning: failed to translate category {story_type.name} -> {language_code}: {exc}", file=sys.stderr)
        translations[story_type.slug] = payload
    return translations


def translate_story(translator: DeepLXTranslator, story: StoryDetail, target_languages: list[str]) -> dict[str, dict[str, str]]:
    translations: dict[str, dict[str, str]] = {}
    for language_code in target_languages:
        if language_code == "zh-Hans":
            continue
        print(f"Translating story {story.story_id} -> {language_code}...")
        translations[language_code] = {
            "title": translator.translate(story.title, "zh-Hans", language_code),
            "intro": translator.translate(story.short_desc or story.content[:220], "zh-Hans", language_code),
            "body_text": translator.translate(story.content, "zh-Hans", language_code),
        }
    return translations


def import_story(
    api_client: StoryAPIClient,
    translator: DeepLXTranslator,
    prompt_writer: ImagePromptWriter,
    flux: FluxImageGenerator,
    supabase,
    bucket: str,
    story_type: StoryType,
    summary: StorySummary,
    settings: Settings,
) -> bool:
    if story_exists(supabase, summary.story_id):
        print(f"Story already exists, skipping: {summary.story_id} {summary.title}")
        return False

    print(f"Fetching detail for story {summary.story_id}: {summary.title}")
    detail = api_client.fetch_story_detail(summary)
    prompts = prompt_writer.build_prompts(detail)
    translations = translate_story(translator, detail, settings.target_languages)

    base_path = f"stories/{detail.slug}"
    card_path = f"{base_path}/card.{settings.image_format}"
    hero_path = f"{base_path}/hero.{settings.image_format}"

    print(f"Generating card image for {detail.slug}...")
    card_bytes = flux.generate(
        prompts["card_prompt"],
        width=settings.card_image_width,
        height=settings.card_image_height,
    )
    upload_image(supabase, bucket, card_path, card_bytes, content_type=f"image/{settings.image_format}")

    print(f"Generating hero image for {detail.slug}...")
    hero_bytes = flux.generate(
        prompts["hero_prompt"],
        width=settings.hero_image_width,
        height=settings.hero_image_height,
    )
    upload_image(supabase, bucket, hero_path, hero_bytes, content_type=f"image/{settings.image_format}")

    insert_story(
        supabase,
        detail,
        category_slug=story_type.slug,
        translations=translations,
        card_image_path=card_path,
        hero_image_path=hero_path,
        prompts=prompts,
        settings=settings,
    )
    print(f"Imported story: {detail.story_id} {detail.title}")
    return True


def main() -> None:
    settings = Settings()
    if not settings.generation_enabled:
        print("Story import disabled by STORY_GENERATION_ENABLED=false. Exiting without changes.")
        return

    settings.require_env()
    api_client = StoryAPIClient(settings)
    translator = DeepLXTranslator(settings)
    prompt_writer = ImagePromptWriter(settings)
    flux = FluxImageGenerator(settings)
    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]

    story_types = api_client.fetch_types()
    if not story_types:
        raise RuntimeError("Story API returned no usable categories")

    existing_category_translations = load_category_translations(
        supabase,
        [story_type.slug for story_type in story_types],
        settings.target_languages,
    )
    category_translations = translate_category_names(
        translator,
        story_types,
        settings.target_languages,
        existing_translations=existing_category_translations,
    )
    sync_story_categories(
        supabase,
        story_types,
        category_translations,
    )

    print(f"Import mode: {len(story_types)} categories")

    imported_count = 0
    skipped_count = 0
    failed_count = 0

    for story_type in story_types:
        page, index = load_import_cursor(supabase, story_type)
        category_imported_count = 0
        print(
            f"Importing category {story_type.type_id} {story_type.name} "
            f"from cursor page={page}, index={index}..."
        )

        while True:
            if category_imported_count >= settings.stories_per_category_per_run:
                break

            summaries = api_client.fetch_story_list_page(story_type, page)
            if not summaries:
                print(f"Category {story_type.name}: page {page} is empty. Cursor remains at page={page}, index=0.")
                save_import_cursor(supabase, story_type, page, 0)
                break

            if index >= len(summaries):
                page += 1
                index = 0
                save_import_cursor(supabase, story_type, page, index)
                continue

            should_stop_category = False
            for current_index in range(index, len(summaries)):
                if category_imported_count >= settings.stories_per_category_per_run:
                    should_stop_category = True
                    break

                summary = summaries[current_index]
                next_page = page
                next_index = current_index + 1
                if next_index >= len(summaries):
                    next_page += 1
                    next_index = 0

                try:
                    did_import = import_story(
                        api_client,
                        translator,
                        prompt_writer,
                        flux,
                        supabase,
                        bucket,
                        story_type,
                        summary,
                        settings,
                    )
                    if did_import:
                        imported_count += 1
                        category_imported_count += 1
                    else:
                        skipped_count += 1
                except Exception as exc:
                    failed_count += 1
                    print(f"Failed story {summary.story_id} {summary.title}: {exc}", file=sys.stderr)
                finally:
                    save_import_cursor(supabase, story_type, next_page, next_index, summary.story_id)
                    print(
                        f"Cursor advanced for {story_type.name}: "
                        f"page={page}, index={current_index}, story_id={summary.story_id} "
                        f"-> next_page={next_page}, next_index={next_index}"
                    )

            if should_stop_category:
                break

            page += 1
            index = 0
            save_import_cursor(supabase, story_type, page, index)

    print("Story import complete")
    print(f"Imported: {imported_count}")
    print(f"Skipped existing: {skipped_count}")
    print(f"Failed: {failed_count}")
