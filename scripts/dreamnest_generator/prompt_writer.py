import time
from typing import Any

from openai import OpenAI

from .config import Settings
from .models import StoryDetail
from .text_utils import safe_json_loads


class ImagePromptWriter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.last_request_at = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        remaining = self.settings.openai_request_delay_seconds - elapsed
        if remaining > 0:
            print(f"Waiting {remaining:.2f}s before OpenAI prompt request...")
            time.sleep(remaining)

    def build_prompts(self, story: StoryDetail) -> dict[str, str]:
        prompt = f"""
You write image prompts for Flux image generation for a children's bedtime story app named DreamNest.

Given a Chinese story title, category, and short description, produce two English Flux prompts:
1. card_prompt: square 1:1 cover image, iconic composition, clear subject, cozy children's book illustration.
2. hero_prompt: vertical 9:16 immersive background image for a story detail page, with safe darker/clean areas for overlaid text.

Rules:
- Return valid JSON only, no markdown.
- Use English prompts only.
- Keep it child-safe, warm, calm, imaginative, picture-book style.
- No text, no letters, no watermark, no UI.
- Avoid scary, violent, realistic horror, weapons, blood, or distressing imagery.
- If humans appear, keep them gentle, stylized, and child-friendly. Prefer animals when appropriate.
- Make hero_prompt suitable as a full-screen background: atmospheric, layered, not too visually noisy.

Story:
- title: {story.title}
- category: {story.type_name}
- short description: {story.short_desc[:900]}

JSON schema:
{{
  "card_prompt": string,
  "hero_prompt": string
}}
""".strip()

        self._wait()
        response = self.client.chat.completions.create(
            model=self.settings.openai_text_model,
            messages=[
                {"role": "system", "content": "You return strict JSON for image prompt generation."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        self.last_request_at = time.monotonic()
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OpenAI returned empty image prompt content")
        payload: dict[str, Any] = safe_json_loads(content)
        card_prompt = str(payload.get("card_prompt", "")).strip()
        hero_prompt = str(payload.get("hero_prompt", "")).strip()
        if not card_prompt or not hero_prompt:
            raise RuntimeError(f"OpenAI returned invalid image prompts: {payload}")
        return {"card_prompt": card_prompt, "hero_prompt": hero_prompt}
