import sys
from typing import Any

from .categories import CATEGORIES, Category
from .config import Settings


def upload_image(supabase, bucket: str, storage_path: str, image_bytes: bytes, settings: Settings) -> str:
    content_type = f"image/{settings.image_format}"
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

        for language_code, name in [
            ("zh-Hans", category["zh"]),
            ("en", category["en"]),
            ("ja", category["ja"]),
            ("ko", category["ko"]),
        ]:
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
