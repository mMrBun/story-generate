import base64
import json
import os
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


def require_env() -> None:
    missing = [key for key in REQUIRED_ENV if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing required env: {', '.join(missing)}")


def today_slug() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"daily-story-{today}"


def safe_json_loads(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON: {content}") from exc


def generate_story(client: OpenAI) -> dict[str, Any]:
    prompt = """
Generate one gentle bedtime story for a children's story app.

Return valid JSON only.

Schema:
{
  "title": string,
  "intro": string,
  "tag": string,
  "duration_minutes": number,
  "cover_prompt": string,
  "hero_prompt": string,
  "pages": [
    {
      "index": number,
      "text": string,
      "image_prompt": string
    }
  ]
}

Rules:
- 3 pages.
- Calm, dreamy, magical, safe for children.
- English text for now.
- Each page should have 1 short paragraph.
- Image prompts should describe cozy illustrated scenes.
- Do not include markdown fences.
- Do not include extra text outside JSON.
"""

    response = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You generate structured JSON for a bedtime story app.",
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

    required_keys = ["title", "pages", "cover_prompt", "hero_prompt"]
    for key in required_keys:
        if key not in story:
            raise RuntimeError(f"Generated story is missing key: {key}")

    if not isinstance(story["pages"], list) or not story["pages"]:
        raise RuntimeError("Generated story pages must be a non-empty list")

    return story


def build_image_prompt(prompt: str) -> str:
    return f"""
Create a cozy illustrated bedtime story image.

Style:
- dreamy children's book illustration
- soft moonlit lighting
- gentle colors
- magical but calm atmosphere
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


def upload_image(
    supabase,
    bucket: str,
    storage_path: str,
    image_bytes: bytes,
) -> str:
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


def normalize_pages(story: dict[str, Any], page_image_paths: dict[int, str]) -> list[dict[str, Any]]:
    pages = []

    for raw_page in story["pages"]:
        page_index = int(raw_page["index"])

        pages.append(
            {
                "index": page_index,
                "text": raw_page["text"],
                "image_path": page_image_paths[page_index],
                "image_prompt": raw_page.get("image_prompt"),
            }
        )

    pages.sort(key=lambda page: page["index"])
    return pages


def main() -> None:
    require_env()

    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
    )

    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]
    slug = today_slug()

    existing = (
        supabase.table("stories")
        .select("id")
        .eq("slug", slug)
        .limit(1)
        .execute()
    )

    if existing.data:
        print(f"Story already exists: {slug}")
        return

    story = generate_story(openai_client)

    base_path = f"stories/{slug}"

    cover_path = f"{base_path}/cover.{IMAGE_FORMAT}"
    hero_path = f"{base_path}/hero.{IMAGE_FORMAT}"

    print("Generating cover image...")
    cover_bytes = generate_image_bytes(openai_client, story["cover_prompt"])
    upload_image(supabase, bucket, cover_path, cover_bytes)

    print("Generating hero image...")
    hero_bytes = generate_image_bytes(openai_client, story["hero_prompt"])
    upload_image(supabase, bucket, hero_path, hero_bytes)

    page_image_paths: dict[int, str] = {}

    for raw_page in story["pages"]:
        page_index = int(raw_page["index"])
        page_prompt = raw_page.get("image_prompt")

        if not page_prompt:
            raise RuntimeError(f"Page {page_index} is missing image_prompt")

        page_path = f"{base_path}/page-{page_index}.{IMAGE_FORMAT}"

        print(f"Generating page {page_index} image...")
        page_bytes = generate_image_bytes(openai_client, page_prompt)
        upload_image(supabase, bucket, page_path, page_bytes)

        page_image_paths[page_index] = page_path

    pages = normalize_pages(story, page_image_paths)

    insert_result = (
        supabase.table("stories")
        .insert(
            {
                "slug": slug,
                "title": story["title"],
                "intro": story.get("intro"),
                "tag": story.get("tag"),
                "duration_minutes": story.get("duration_minutes", 10),
                "cover_image_path": cover_path,
                "thumbnail_image_path": cover_path,
                "hero_image_path": hero_path,
                "pages": pages,
                "source_model": TEXT_MODEL,
                "image_model": IMAGE_MODEL,
                "generation_prompt": "daily bedtime story generation",
                "is_published": False,
                "published_at": None,
            }
        )
        .execute()
    )

    print(f"Generated story: {story['title']}")
    print(f"Slug: {slug}")
    print(f"Inserted rows: {len(insert_result.data or [])}")
    print(f"Images uploaded under: {base_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to generate daily story: {exc}", file=sys.stderr)
        raise
