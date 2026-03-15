# GameSeed runner_v1

GameSeed is a template-driven prompt-to-game pipeline that turns a text prompt into a playable Phaser endless runner. It provides a small studio UI, an async FastAPI backend, and a manifest-driven runtime that can use Tripo for foreground sprites, BytePlus for layered backgrounds, and Gemini for bounded spec and manifest validation.

Tripo Asset creation done in : https://github.com/divyansh7877/tripo-asset

## What This Repo Contains

- FastAPI backend for job creation, polling, manifest delivery, and the play page
- Studio UI at `/` for prompts, reference images, status, and play links
- Phaser `runner_v1` frontend that loads only from a generated manifest
- Planner and manifest builder for a constrained endless-runner template
- Provider adapters for:
  - Tripo foreground assets
  - BytePlus ModelArk background layers
  - Gemini manifest validation and spec refinement
- File-based storage for jobs, uploads, and provider caches under `data/`

## Requirements

- Python 3.11+
- A separate running Tripo asset service if you want real character and obstacle assets
- Optional API keys:
  - `ARK_API_KEY` for BytePlus backgrounds
  - `GEMINI_API_KEY` for Gemini validation and spec refinement

The app still runs without these providers, but it will fall back to placeholder assets.

## Project Layout

```text
app/
  main.py               FastAPI routes and HTML shells
  jobs.py               async orchestration pipeline
  planner.py            prompt normalization and asset planning
  manifest.py           final Phaser manifest assembly
  validator.py          Gemini validation/refinement layer
  providers/            Tripo and BytePlus integrations
  static/               dashboard UI and Phaser runtime
tests/                  planner, pipeline, validator, and image tests
data/                   generated jobs, caches, and uploads at runtime
```

## 1. Clone And Install

```bash
git clone <your-repo-url>
cd gameseed
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## 2. Configure Environment

Create a local env file:

```bash
cp .env.example .env
```

Set the values you need in `.env`:

```env
PUBLIC_BASE_URL=http://127.0.0.1:8000
DATA_ROOT=data

TRIPO_ASSET_BASE_URL=http://127.0.0.1:8001
TRIPO_POLL_INTERVAL_SECONDS=3.0
TRIPO_TIMEOUT_SECONDS=300.0

ARK_API_KEY=
BYTEPLUS_BASE_URL=https://ark.ap-southeast.bytepluses.com/api/v3
BYTEPLUS_MODEL=seedream-3-0-t2i-250415
BYTEPLUS_IMAGE_SIZE=1024x1024
BYTEPLUS_TIMEOUT_SECONDS=60.0

GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta
ENABLE_GEMINI_VALIDATION=true

PHASER_CDN_URL=https://cdn.jsdelivr.net/npm/phaser@3/dist/phaser.min.js
DEFAULT_VIEWPORT_WIDTH=1280
DEFAULT_VIEWPORT_HEIGHT=720
```

## 3. Run The Tripo Asset Service

This repo expects a separate Tripo service running at `TRIPO_ASSET_BASE_URL`. If you are using the sibling repo at `/Users/divagarwal/Projects/gamejam/tripo-asset`, a local setup looks like this:

```bash
cd /Users/divagarwal/Projects/gamejam/tripo-asset
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set at least:

```env
TRIPO_API_KEY=your_tripo_key
PUBLIC_BASE_URL=http://127.0.0.1:8001
```

Then start it:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## 4. Run GameSeed

From this repo:

```bash
cd /path/to/gameseed
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open the studio UI:

- [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

## 5. Generate A Game

### Studio UI

Use the browser UI to submit:

- the main game prompt
- optional character prompt override
- optional obstacle prompts
- optional background prompt
- optional reference images for general, character, obstacle, and background guidance

The UI shows job status and links to:

- the job JSON
- the generated manifest
- the playable game page

### API

You can also create a job directly:

```bash
curl -X POST http://127.0.0.1:8000/games/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "cyberpunk neon courier running across rooftop billboards",
    "difficulty": "normal",
    "audience": "general",
    "session_length_sec": 90
  }'
```

Poll the job:

```bash
curl http://127.0.0.1:8000/games/<job_id>
```

When the job is done:

- `GET /games/<job_id>/manifest`
- `GET /games/play/<job_id>`

## API Surface

- `GET /` Studio UI
- `GET /health` Health check
- `POST /games/generate` JSON job creation
- `POST /games/generate-form` multipart job creation for the UI
- `GET /games` List jobs
- `GET /games/{job_id}` Fetch a single job
- `GET /games/{job_id}/manifest` Fetch the final manifest
- `GET /games/play/{job_id}` Open the playable Phaser runner

## How The Pipeline Works

1. The request is normalized into a constrained `RunnerSpec`.
2. The planner creates a fixed asset plan:
   - 1 character
   - 3 obstacle variants
   - 1 collectible
   - 3 background layers
3. Tripo is used for the foreground assets.
4. BytePlus is used for the parallax background layers.
5. Gemini can refine the runner spec and review the final manifest.
6. The manifest is written and the Phaser client loads it at runtime.

## Running Tests

```bash
pytest -q
```

## Notes

- `data/` contains runtime jobs, uploads, caches, manifests, and generated assets. It should not be committed.
- `.env` should not be committed.
- The Phaser runtime is loaded from jsDelivr by default, so the browser needs internet access unless you replace `PHASER_CDN_URL`.
- `runner_v1` is intentionally constrained. Prompt personalization changes art direction and tuning, not core gameplay structure.
