# DreamNest Story Importer

This project imports stories from the mxnzp story API, translates them through DeepLX, generates two images with Cloudflare Flux, uploads images to Supabase Storage, and writes rows into Supabase.

## What It Does

- Story categories come from `GET /api/story/types`.
- `童话作文` is excluded.
- Story lists come from `GET /api/story/list?type_id=...&page=...`.
- Each category keeps a database cursor in `story_import_cursors`, so future runs continue from the last scanned page/index.
- Story detail comes from `GET /api/story/details?story_id=...`.
- DeepLX translates title, intro, and body to `en`, `ja`, and `ko`.
- OpenAI only creates two English Flux prompts from the title and short description.
- Cloudflare Flux generates two images per story:
  - card image: `1008x1008`
  - hero/detail background image: `752x1328`
- Stories are stored as one long `body_text`.

## Structure

- `scripts/generate_daily_story.py`: entrypoint.
- `scripts/dreamnest_generator/config.py`: secrets, URLs, and fixed product defaults.
- `scripts/dreamnest_generator/story_api.py`: mxnzp story API client with QPS pacing.
- `scripts/dreamnest_generator/translator.py`: DeepLX translation client.
- `scripts/dreamnest_generator/prompt_writer.py`: OpenAI image prompt generation.
- `scripts/dreamnest_generator/flux_api.py`: Cloudflare Flux image generation.
- `scripts/dreamnest_generator/repository.py`: Supabase table/storage writes.
- `scripts/dreamnest_generator/pipeline.py`: orchestration.

## Required Secrets

Set these in GitHub repository secrets or local `.env`:

- `MXNZP_APP_ID`
- `MXNZP_APP_SECRET`
- `DEEPLX_URL`
- `DEEPLX_TOKEN`
- `OPENAI_API_KEY`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_STORAGE_BUCKET`

Optional connection secret:

- `DEEPLX_URLS`: comma-separated DeepLX endpoints. If set, requests rotate across these endpoints.

Do not hardcode secrets in the public repository.

## Workflow Variables

Only two process controls are intended for daily use:

- `STORY_GENERATION_ENABLED=true`: set to `false` to make the job exit without importing.
- `STORIES_PER_CATEGORY_PER_RUN=3`: successful new stories to import for each category per run.

Everything else is a fixed product default in `config.py`, not a GitHub variable.

## Local Run

```bash
uv sync
uv run python scripts/generate_daily_story.py
```

Example `.env` process controls:

```env
STORY_GENERATION_ENABLED=true
STORIES_PER_CATEGORY_PER_RUN=3
```

## Database

Run the SQL migration in the iOS project before importing:

```text
/Users/bun/projects/swiftProjects/dream-nest/database/story_api_migration.sql
```
