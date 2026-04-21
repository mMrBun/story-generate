import json
import re
from typing import Any


def safe_json_loads(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON: {content}") from exc


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def total_words(pages: list[dict[str, Any]]) -> int:
    return sum(word_count(str(page.get("text", ""))) for page in pages)


def non_space_char_count(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def total_non_space_chars(pages: list[dict[str, Any]]) -> int:
    return sum(non_space_char_count(str(page.get("text", ""))) for page in pages)


def page_non_space_chars(page: dict[str, Any]) -> int:
    return non_space_char_count(str(page.get("text", "")))


def joined_page_text(pages: list[dict[str, Any]]) -> str:
    return "\n".join(str(page.get("text", "")) for page in pages)


def normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", "", value.lower())


def story_text_for_prompt(story: dict[str, Any]) -> str:
    page_text = "\n".join(
        f"Page {page['index']}: {page['text']}"
        for page in story["pages"]
    )
    return f"Title: {story['title']}\nIntro: {story.get('intro', '')}\n{page_text}"
