import time
from typing import Any

import requests

from .config import Settings
from .models import StoryDetail, StorySummary, StoryType
from .text_utils import normalize_story_text


class StoryAPIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.last_request_at = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        remaining = self.settings.story_api_request_delay_seconds - elapsed
        if remaining > 0:
            print(f"Waiting {remaining:.2f}s for story API QPS limit...")
            time.sleep(remaining)

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        self._wait()
        url = f"{self.settings.mxnzp_base_url}/{endpoint.lstrip('/')}"
        params = {
            **params,
            "app_id": self.settings.mxnzp_app_id,
            "app_secret": self.settings.mxnzp_app_secret,
        }
        response = self.session.get(url, params=params, timeout=30)
        self.last_request_at = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 1:
            raise RuntimeError(f"Story API error for {endpoint}: {payload}")
        return payload

    def fetch_types(self) -> list[StoryType]:
        payload = self._get("types", {})
        excluded = set(self.settings.excluded_story_type_names)
        types = []
        for raw in payload.get("data") or []:
            name = str(raw.get("name", "")).strip()
            if not name or name in excluded:
                continue
            types.append(StoryType(type_id=int(raw["type_id"]), name=name))
        return types


    def fetch_story_list_page(self, story_type: StoryType, page: int) -> list[StorySummary]:
        payload = self._get("list", {"type_id": story_type.type_id, "page": page})
        rows = payload.get("data") or []
        stories: list[StorySummary] = []

        for raw in rows:
            story_id = int(raw["storyId"])
            stories.append(
                StorySummary(
                    story_id=story_id,
                    title=str(raw.get("title", "")).strip(),
                    type_name=str(raw.get("type", story_type.name)).strip() or story_type.name,
                    length=int(raw.get("length") or 0),
                    read_time=str(raw.get("readTime", "")),
                    short_desc=normalize_story_text(str(raw.get("shortDesc", ""))),
                    type_id=story_type.type_id,
                )
            )

        return stories

    def fetch_story_detail(self, summary: StorySummary) -> StoryDetail:
        payload = self._get("details", {"story_id": summary.story_id})
        raw = payload.get("data") or {}
        content = normalize_story_text(str(raw.get("content", "")))
        if not content:
            raise RuntimeError(f"Story {summary.story_id} has empty content")

        return StoryDetail(
            story_id=int(raw.get("storyId", summary.story_id)),
            title=str(raw.get("title", summary.title)).strip() or summary.title,
            type_name=str(raw.get("type", summary.type_name)).strip() or summary.type_name,
            length=int(raw.get("length") or summary.length or len(content)),
            read_time=str(raw.get("readTime", summary.read_time)),
            content=content,
            short_desc=summary.short_desc,
            type_id=summary.type_id,
        )
