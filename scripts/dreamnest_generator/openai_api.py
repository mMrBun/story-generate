import base64
import time
from typing import Any

from openai import OpenAI

from .categories import Category
from .config import Settings
from .prompts import build_canonical_story_prompt, build_image_prompt, build_translation_prompt
from .text_utils import safe_json_loads
from .validators import validate_canonical_story, validate_story_title, validate_translated_story


def wait_before_request(seconds: float, label: str) -> None:
    if seconds <= 0:
        return
    print(f"Waiting {seconds:g}s before {label} to stay under request rate limits...")
    time.sleep(seconds)


def generate_canonical_story(client: OpenAI, category: Category, slug: str, settings: Settings) -> dict[str, Any]:
    prompt = build_canonical_story_prompt(category, slug, settings)
    wait_before_request(settings.text_request_delay_seconds, "text generation request")
    response = client.chat.completions.create(
        model=settings.text_model,
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
    story = validate_canonical_story(story, category, settings)
    story["slug"] = slug
    story["category_slug"] = category["slug"]
    story["language_code"] = settings.source_language
    return story


def translate_story(client: OpenAI, canonical_story: dict[str, Any], target_language: str, category: Category, settings: Settings) -> dict[str, Any]:
    source_language = str(canonical_story.get("language_code", settings.source_language))
    if target_language == source_language:
        validate_story_title(str(canonical_story["title"]), category, source_language)
        return {
            "language_code": source_language,
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

    prompt = build_translation_prompt(canonical_story, target_language, category, settings)
    wait_before_request(settings.text_request_delay_seconds, f"{target_language} translation request")
    response = client.chat.completions.create(
        model=settings.text_model,
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
    return validate_translated_story(
        translated,
        category,
        target_language,
        settings,
        expected_page_count=len(canonical_story["pages"]),
    )


def generate_image_bytes(client: OpenAI, prompt: str, settings: Settings) -> bytes:
    wait_before_request(settings.image_request_delay_seconds, "image generation request")
    response = client.images.generate(
        model=settings.image_model,
        prompt=build_image_prompt(prompt),
        size=settings.image_size,
        quality=settings.image_quality,
        output_format=settings.image_format,
        n=1,
    )

    if not response.data:
        raise RuntimeError("OpenAI image generation returned no data")

    image_base64 = response.data[0].b64_json
    if not image_base64:
        raise RuntimeError("OpenAI image generation returned empty b64_json")

    return base64.b64decode(image_base64)
