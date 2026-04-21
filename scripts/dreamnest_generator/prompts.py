from typing import Any

from .categories import Category, source_category_meaning
from .config import Settings, language_profiles
from .text_utils import story_text_for_prompt


def source_language_profile(settings: Settings) -> dict[str, str]:
    profile = language_profiles(settings).get(settings.source_language)
    if not profile:
        raise RuntimeError(f"Unsupported source language: {settings.source_language}")
    return profile


def source_length_rule(settings: Settings) -> str:
    if settings.source_language in {"zh-Hans", "ja", "ko"}:
        return (
            f"The story body must be at least {settings.min_source_cjk_chars} non-space characters "
            f"in the source language. Page lengths may vary naturally, but do not make the story feel like a summary."
        )
    return f"The story body must be at least {settings.min_source_words} English words in total."


def build_canonical_story_prompt(category: Category, slug: str, settings: Settings) -> str:
    profile = source_language_profile(settings)
    return f"""
You are a children's bedtime story writer for an app called DreamNest.

Generate one original long-form bedtime story in {profile['name']}.

Category:
- slug: {category['slug']}
- Chinese name: {category['zh']}
- English name: {category['en']}
- Meaning: {source_category_meaning(category, settings.source_language)}

Return valid JSON only. No markdown. No extra commentary.

JSON schema:
{{
  "slug": "{slug}",
  "category_slug": "{category['slug']}",
  "language_code": "{settings.source_language}",
  "title": string,
  "intro": string,
  "duration_minutes": number,
  "cover_prompt": string,
  "hero_prompt": string,
  "pages": [
    {{
      "index": number,
      "text": string,
      "image_prompt": string
    }}
  ]
}}

Hard requirements:
- language_code must be exactly "{settings.source_language}".
- {source_length_rule(settings)}
- Split the story into {settings.min_page_count}-{settings.max_page_count} pages. Aim for about {settings.page_count} pages, but do not force the count if the story reads better with a nearby number.
- Each page should be a complete, substantial paragraph. Never return fewer than {settings.min_page_count} pages.
- If writing Simplified Chinese, the total story length matters more than identical page lengths. Let page lengths vary naturally, but avoid tiny summary pages.
- category_slug must be exactly "{category['slug']}".
- slug must be exactly "{slug}".
- The story must be calm, concrete, warm, and suitable before sleep.
- The title must be a unique literary story title, not the category name, not the category slug, and not a generic label.
- The category value should emerge naturally through the plot, not as a lecture.
- Avoid violence, horror, death, weapons, punishment, shame, or intense conflict.
- Do not reference or imitate existing copyrighted characters, franchises, or famous fairy tales.
- cover_prompt, hero_prompt, and image_prompt must be in English.
- Image prompts should describe cozy children's-book illustrations with animal characters only, no humans, no text, no watermark, and no UI.

Chinese story style rules, if writing Simplified Chinese:
- Write like a native Chinese children's story, not translated prose.
- Prefer clear cause and effect, everyday actions, small mistakes, dialogue, and concrete details children can picture.
- Use short and medium-length sentences. Avoid ornate metaphors piled on top of each other.
- Do not overuse abstract words such as 温柔, 善意, 心灵, 梦想, 光芒, 星光, 呼吸, 低语, 编织.
- Avoid AI-flavored sentence patterns like "不是……而是……", "这将是……", "他们明白了最深的真理", or repeatedly explaining the theme by name.
- The moral should come from what the character does and loses or gains, like a simple fable. It should not read like a speech.
- Use one main animal protagonist with a memorable small flaw or wish. Supporting characters should have simple roles.
- Include natural spoken dialogue with Chinese quotation marks.
- Keep bedtime warmth, but let each page move the plot forward.
- Page text must be story prose only. Never describe the illustration, camera, scene, page, frame, or "final image" inside the story text.
- Do not write meta narration such as "最后一个画面是这样", "这个画面", "镜头里", "插画中", or "场景是".
- The final page must end the plot from inside the story world. It must not introduce itself as a picture, ending card, or visual composition.
""".strip()


def build_translation_prompt(canonical_story: dict[str, Any], target_language: str, category: Category, settings: Settings) -> str:
    profiles = language_profiles(settings)
    source_language = str(canonical_story.get("language_code", settings.source_language))
    profile = profiles.get(target_language)
    if not profile:
        raise RuntimeError(f"Unsupported target language: {target_language}")

    return f"""
Translate the following DreamNest bedtime story from {profiles.get(source_language, {}).get('name', source_language)} into {profile['name']}.

Return valid JSON only. No markdown. No extra commentary.

Target language code: {target_language}

JSON schema:
{{
  "language_code": "{target_language}",
  "title": string,
  "intro": string,
  "pages": [
    {{
      "index": number,
      "text": string
    }}
  ]
}}

Translation requirements:
- Preserve the plot, exact page count, page order, emotional tone, and bedtime pacing.
- Translate title, intro, and every page text.
- The translated title must still be a story title, not the category name.
- Do not translate image prompts; image prompts are stored separately from the canonical story.
- Do not summarize, shorten, omit scenes, or add new plot events.
- {profile['length_rule']}
- {profile['style_rule']}
- Use natural native prose in the target language, not word-for-word translation.
- Keep dialogue lively and simple. Preserve concrete actions and cause-and-effect.

Source story:
{story_text_for_prompt(canonical_story)}
""".strip()


def build_image_prompt(prompt: str) -> str:
    return f"""
Create a cozy illustrated bedtime story image.

Style:
- high-quality hand-painted children's picture book illustration
- watercolor and gouache texture, clean shapes, soft edges
- warm indoor or gentle outdoor lighting that fits the scene
- calm, safe, soothing composition
- animal characters only, no human characters
- simplified expressive animal faces, not realistic faces
- medium or wide shot; avoid extreme close-ups and portrait framing
- keep faces small enough to remain clean and charming
- natural anatomy for animals; clear paws, no malformed limbs
- no scary elements
- no text, no watermark, no UI, no letters

Scene:
{prompt}
""".strip()
