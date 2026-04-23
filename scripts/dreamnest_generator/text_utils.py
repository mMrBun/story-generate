import json
import math
import re
from typing import Any


def safe_json_loads(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON: {content}") from exc


def normalize_story_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for raw_line in normalized.split("\n"):
        line = raw_line.strip().strip("\u3000").strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


def clean_preview_text(text: str, max_length: int = 160) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].rstrip() + "..."


def read_time_to_minutes(value: str, fallback_length: int = 0) -> int:
    parts = value.strip().split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = [int(part) for part in parts]
            total_seconds = hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = [int(part) for part in parts]
            total_seconds = minutes * 60 + seconds
        else:
            total_seconds = 0
    except ValueError:
        total_seconds = 0

    if total_seconds <= 0 and fallback_length > 0:
        # Chinese children's stories are usually read around 220-280 chars/minute.
        return max(1, math.ceil(fallback_length / 240))

    return max(1, math.ceil(total_seconds / 60))


def estimated_reading_minutes(text: str) -> int:
    compact = re.sub(r"\s+", "", text)
    return max(1, math.ceil(len(compact) / 240))
