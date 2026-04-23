from datetime import datetime, timezone

from .config import Settings
from .models import StoryDetail, StoryType
from .text_utils import clean_preview_text, estimated_reading_minutes, read_time_to_minutes



def upload_image(supabase, bucket: str, storage_path: str, image_bytes: bytes, content_type: str = "image/png") -> str:
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


def load_category_translations(supabase, category_slugs: list[str], language_codes: list[str]) -> dict[str, dict[str, str]]:
    if not category_slugs or not language_codes:
        return {}

    rows = (
        supabase.table("story_category_translations")
        .select("category_slug,language_code,name")
        .in_("category_slug", category_slugs)
        .in_("language_code", language_codes)
        .execute()
    )

    translations: dict[str, dict[str, str]] = {}
    for row in rows.data or []:
        slug = row.get("category_slug")
        language_code = row.get("language_code")
        name = row.get("name")
        if slug and language_code and name:
            translations.setdefault(slug, {})[language_code] = name
    return translations


def load_import_cursor(supabase, story_type: StoryType) -> tuple[int, int]:
    existing = (
        supabase.table("story_import_cursors")
        .select("next_page,next_index")
        .eq("source_provider", "mxnzp")
        .eq("category_slug", story_type.slug)
        .limit(1)
        .execute()
    )
    if not existing.data:
        return 1, 0

    row = existing.data[0]
    next_page = int(row.get("next_page") or 1)
    next_index = int(row.get("next_index") or 0)
    return max(next_page, 1), max(next_index, 0)


def save_import_cursor(supabase, story_type: StoryType, next_page: int, next_index: int, last_story_id: int | None = None) -> None:
    payload = {
        "source_provider": "mxnzp",
        "category_slug": story_type.slug,
        "source_type_id": story_type.type_id,
        "source_type_name": story_type.name,
        "next_page": max(next_page, 1),
        "next_index": max(next_index, 0),
        "last_story_id": str(last_story_id) if last_story_id is not None else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("story_import_cursors").upsert(
        payload,
        on_conflict="source_provider,category_slug",
    ).execute()


def story_exists(supabase, source_story_id: int) -> bool:
    existing = (
        supabase.table("stories")
        .select("id")
        .eq("source_provider", "mxnzp")
        .eq("source_story_id", str(source_story_id))
        .limit(1)
        .execute()
    )
    return bool(existing.data)


def sync_story_categories(
    supabase,
    story_types: list[StoryType],
    translations_by_slug: dict[str, dict[str, str]],
) -> None:
    # Categories from the upstream API are treated as an append/update dictionary.
    # We never delete local categories here because existing stories may reference them.
    for sort_order, story_type in enumerate(story_types, start=1):
        supabase.table("story_categories").upsert(
            {
                "slug": story_type.slug,
                "source_type_id": story_type.type_id,
                "source_name": story_type.name,
                "sort_order": sort_order * 10,
            },
            on_conflict="slug",
        ).execute()

        translations = translations_by_slug.get(story_type.slug, {"zh-Hans": story_type.name})
        for language_code, name in translations.items():
            supabase.table("story_category_translations").upsert(
                {
                    "category_slug": story_type.slug,
                    "language_code": language_code,
                    "name": name,
                },
                on_conflict="category_slug,language_code",
            ).execute()


def insert_story(
    supabase,
    story: StoryDetail,
    category_slug: str,
    translations: dict[str, dict[str, str]],
    card_image_path: str,
    hero_image_path: str,
    prompts: dict[str, str],
    settings: Settings,
) -> None:
    duration_minutes = read_time_to_minutes(story.read_time, story.length) or estimated_reading_minutes(story.content)
    intro = clean_preview_text(story.short_desc or story.content)
    now = datetime.now(timezone.utc).isoformat()
    pages = [
        {
            "index": 1,
            "text": story.content,
            "image_path": hero_image_path,
            "image_prompt": prompts["hero_prompt"],
        }
    ]

    supabase.table("stories").upsert(
        {
            "slug": story.slug,
            "title": story.title,
            "intro": intro,
            "tag": story.type_name,
            "category_slug": category_slug,
            "content_language": "zh-Hans",
            "body_text": story.content,
            "source_provider": "mxnzp",
            "source_story_id": str(story.story_id),
            "source_type_id": story.type_id,
            "source_type_name": story.type_name,
            "duration_minutes": duration_minutes,
            "cover_image_path": card_image_path,
            "thumbnail_image_path": card_image_path,
            "hero_image_path": hero_image_path,
            "pages": pages,
            "source_model": "mxnzp-story-api + deeplx",
            "image_model": settings.flux_model,
            "generation_prompt": f"card={prompts['card_prompt']}\nhero={prompts['hero_prompt']}",
            "is_published": True,
            "published_at": now,
        },
        on_conflict="slug",
    ).execute()

    source_payload = {
        "title": story.title,
        "intro": intro,
        "body_text": story.content,
    }
    merged_translations = {"zh-Hans": source_payload, **translations}

    for language_code, payload in merged_translations.items():
        body_text = payload["body_text"]
        translated_pages = [
            {
                "index": 1,
                "text": body_text,
                "image_path": hero_image_path,
                "image_prompt": prompts["hero_prompt"],
            }
        ]
        supabase.table("story_translations").upsert(
            {
                "story_slug": story.slug,
                "language_code": language_code,
                "title": payload["title"],
                "intro": payload["intro"],
                "tag_line": story.type_name,
                "body_text": body_text,
                "pages": translated_pages,
            },
            on_conflict="story_slug,language_code",
        ).execute()
