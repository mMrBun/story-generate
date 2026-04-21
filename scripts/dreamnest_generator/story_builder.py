from typing import Any


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
