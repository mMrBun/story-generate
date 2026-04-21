# Daily Story Generator

This project generates DreamNest bedtime stories, uploads illustrations to Supabase Storage, and writes story rows plus translations into Supabase.

## Structure

- `scripts/generate_daily_story.py`: tiny entrypoint used by GitHub Actions and local runs.
- `scripts/dreamnest_generator/config.py`: environment variables and runtime settings.
- `scripts/dreamnest_generator/categories.py`: story categories and category translations.
- `scripts/dreamnest_generator/prompts.py`: story, translation, and image prompts.
- `scripts/dreamnest_generator/validators.py`: story length, page count, title, and Chinese style validation.
- `scripts/dreamnest_generator/openai_api.py`: OpenAI text/image calls and request pacing.
- `scripts/dreamnest_generator/repository.py`: Supabase table/storage writes.
- `scripts/dreamnest_generator/pipeline.py`: main orchestration.

## Required Secrets

Set these in GitHub repository secrets:

- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_STORAGE_BUCKET`

## Optional GitHub Variables

Set these in GitHub repository variables, not secrets. The workflow provides safe defaults if you do not set them.

- `STORY_GENERATION_ENABLED=true`: master switch. Set to `false` to make the Action exit without generating anything.
- `GENERATE_ALL_CATEGORIES=false`: set to `true` to generate one story for every category in one run.
- `TARGET_LANGUAGES=zh-Hans,en,ja,ko`: languages written to `story_translations`.
- `PUBLISH_IMMEDIATELY=false`: set to `true` if newly generated stories should appear in the app immediately.
- `MAX_CATEGORIES_PER_RUN=0`: `0` means no cap. Use a number like `3` if you want to backfill gradually.
- `STORY_MIN_PAGE_COUNT=6`: minimum generated pages for one story.
- `STORY_MAX_PAGE_COUNT=10`: maximum generated pages for one story.
- `CONTINUE_ON_CATEGORY_FAILURE=true`: in full-category mode, continue with later categories if one category fails.
- `OPENAI_TEXT_REQUEST_DELAY_SECONDS=2`: delay before each text/translation request.
- `OPENAI_IMAGE_REQUEST_DELAY_SECONDS=12`: delay before each image request.
- `BATCH_CATEGORY_DELAY_SECONDS=30`: delay between categories when `GENERATE_ALL_CATEGORIES=true`.

## Batch Generation Notes

`GENERATE_ALL_CATEGORIES=true` is supported. The pipeline remains strictly sequential and adds configurable delays before text requests, image requests, and category batches. This is intentional: one story can require several text calls and many image calls, so a full-category run can otherwise hit model request-per-minute limits quickly.

For a fresh empty database, use one of these approaches:

1. Full backfill: `GENERATE_ALL_CATEGORIES=true`, keep the default delays, and let the workflow run.
2. Safer staged backfill: `GENERATE_ALL_CATEGORIES=true` plus `MAX_CATEGORIES_PER_RUN=2` or `3`, then run manually a few times.

## Current Defaults

- `OPENAI_TEXT_MODEL=gpt-5-mini`
- `OPENAI_IMAGE_MODEL=gpt-image-1`
- `OPENAI_IMAGE_QUALITY=medium`
- `STORY_SOURCE_LANGUAGE=zh-Hans`
- `TARGET_LANGUAGES=zh-Hans,en,ja,ko`
- `STORY_MIN_SOURCE_CJK_CHARS=1200`
- `STORY_PAGE_COUNT=8` as the target page count, not a hard exact requirement
- `STORY_MIN_PAGE_COUNT=6`
- `STORY_MAX_PAGE_COUNT=10`

The generation pipeline writes the canonical story in Simplified Chinese first, then translates it into the target languages. This preserves the story quality you preferred while still supporting multilingual display in the app.

The validator now treats page count as a range. `STORY_PAGE_COUNT` is only the target count used in the prompt; a generated story passes as long as it has `STORY_MIN_PAGE_COUNT` through `STORY_MAX_PAGE_COUNT` pages and meets the total length floor. This avoids rejecting good stories just because they naturally use 6 or 7 pages.

## Local Run

```bash
uv sync
uv run python scripts/generate_daily_story.py
```

Use `.env` locally for secrets and variables.
