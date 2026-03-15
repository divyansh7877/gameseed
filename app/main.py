from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.jobs import GameJobManager
from app.models import GameJob, GameJobStatus, GenerateGameRequest
from app.providers.byteplus import BytePlusBackgroundProvider
from app.providers.tripo import TripoForegroundProvider
from app.storage import GameStorage
from app.validator import GeminiManifestValidator

_settings = get_settings()
_settings.data_root.mkdir(parents=True, exist_ok=True)


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GameSeed Studio</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body class="dashboard-page">
    <div class="dashboard-shell">
      <aside class="dashboard-panel dashboard-panel--hero">
        <p class="eyebrow">runner_v1 studio</p>
        <h1>Generate runner games from prompts, references, and scene direction.</h1>
        <p class="lede">
          Submit a game concept, optional reference images for characters, obstacles, and backgrounds,
          then monitor generation status and open the finished game.
        </p>
        <div class="capabilities">
          <div class="capability-card">
            <h2>Foreground</h2>
            <p>Tripo handles the character, obstacle set, and collectible silhouettes.</p>
          </div>
          <div class="capability-card">
            <h2>Backgrounds</h2>
            <p>BytePlus or local fallbacks build layered runner scenery for the parallax stack.</p>
          </div>
        </div>
      </aside>
      <main class="dashboard-content">
        <section class="dashboard-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">new job</p>
              <h2>Create a Game</h2>
            </div>
            <span id="submit-status" class="pill">Idle</span>
          </div>
          <form id="generate-form" class="generator-form">
            <label>
              <span>Game prompt</span>
              <textarea name="prompt" rows="4" placeholder="Cyberpunk neon courier sprinting across dangerous rooftop billboards" required></textarea>
            </label>
            <div class="grid-3">
              <label>
                <span>Difficulty</span>
                <select name="difficulty">
                  <option value="easy">Easy</option>
                  <option value="normal" selected>Normal</option>
                  <option value="hard">Hard</option>
                </select>
              </label>
              <label>
                <span>Audience</span>
                <select name="audience">
                  <option value="kids">Kids</option>
                  <option value="teen">Teen</option>
                  <option value="general" selected>General</option>
                </select>
              </label>
              <label>
                <span>Run length</span>
                <select name="session_length_sec">
                  <option value="60">60s</option>
                  <option value="90" selected>90s</option>
                  <option value="120">120s</option>
                </select>
              </label>
            </div>

            <div class="grid-2">
              <label>
                <span>Character prompt</span>
                <textarea name="character_prompt" rows="3" placeholder="Optional override for the player character"></textarea>
              </label>
              <label>
                <span>Character images</span>
                <input type="file" name="character_images" multiple accept="image/*">
              </label>
            </div>

            <div class="grid-2">
              <label>
                <span>Obstacle prompts</span>
                <textarea name="obstacle_prompt_text" rows="4" placeholder="One obstacle prompt per line"></textarea>
              </label>
              <label>
                <span>Obstacle images</span>
                <input type="file" name="obstacle_images" multiple accept="image/*">
              </label>
            </div>

            <div class="grid-2">
              <label>
                <span>Background prompt</span>
                <textarea name="background_prompt" rows="3" placeholder="Optional override for the scene or environment"></textarea>
              </label>
              <label>
                <span>Background images</span>
                <input type="file" name="background_images" multiple accept="image/*">
              </label>
            </div>

            <label>
              <span>General reference images</span>
              <input type="file" name="reference_images" multiple accept="image/*">
            </label>

            <button type="submit" id="submit-button">Generate Game</button>
          </form>
        </section>

        <section class="dashboard-panel">
          <div class="panel-header">
            <div>
              <p class="eyebrow">jobs</p>
              <h2>Recent Games</h2>
            </div>
            <button id="refresh-jobs" class="ghost-button" type="button">Refresh</button>
          </div>
          <div id="jobs-empty" class="empty-state">No jobs yet. Submit a prompt to start one.</div>
          <div id="jobs-list" class="jobs-list"></div>
        </section>
      </main>
    </div>
    <script src="/static/dashboard.js"></script>
  </body>
</html>"""


def _play_html(manifest_url: str, phaser_cdn_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GameSeed Runner</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <div id="app">
      <div class="shell">
        <div class="sidebar">
          <h1>GameSeed</h1>
          <p class="status">Manifest-driven runner_v1</p>
          <div id="meta"></div>
          <button id="restart">Restart</button>
        </div>
        <div class="stage">
          <div id="game-root"></div>
        </div>
      </div>
    </div>
    <script>
      window.GAME_MANIFEST_URL = {manifest_url!r};
    </script>
    <script src="{phaser_cdn_url}"></script>
    <script src="/static/game.js"></script>
  </body>
</html>"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    storage = GameStorage(settings.data_root)
    manager = GameJobManager(
        settings=settings,
        storage=storage,
        foreground_provider=TripoForegroundProvider(settings, storage),
        background_provider=BytePlusBackgroundProvider(settings, storage),
        validator=GeminiManifestValidator(settings),
    )
    app.state.settings = settings
    app.state.storage = storage
    app.state.job_manager = manager
    yield
    await manager.close()


app = FastAPI(title="GameSeed runner_v1", version="0.1.0", lifespan=lifespan)
app.mount("/files", StaticFiles(directory=str(_settings.data_root)), name="files")
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def _manager(request: Request) -> GameJobManager:
    return request.app.state.job_manager


def _base_url(request: Request) -> str:
    configured = request.app.state.settings.public_base_url
    runtime = str(request.base_url).rstrip("/")
    return configured.rstrip("/") if configured else runtime


async def _store_uploads(request: Request, group: str, files: list[UploadFile]) -> list[str]:
    if not files:
        return []
    upload_root = request.app.state.storage.uploads_dir() / group / str(uuid4())
    upload_root.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        destination = upload_root / upload.filename
        destination.write_bytes(await upload.read())
        saved_paths.append(str(destination))
    return saved_paths


@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=_dashboard_html())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/games/generate", response_model=GameJob)
async def generate_game(request_body: GenerateGameRequest, request: Request) -> GameJob:
    try:
        return await _manager(request).create_job(request_body, _base_url(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/games/generate-form", response_model=GameJob)
async def generate_game_form(
    request: Request,
    prompt: str = Form(...),
    difficulty: str = Form("normal"),
    audience: str = Form("general"),
    session_length_sec: int = Form(90),
    character_prompt: str = Form(""),
    obstacle_prompt_text: str = Form(""),
    background_prompt: str = Form(""),
    reference_images: list[UploadFile] = File(default_factory=list),
    character_images: list[UploadFile] = File(default_factory=list),
    obstacle_images: list[UploadFile] = File(default_factory=list),
    background_images: list[UploadFile] = File(default_factory=list),
) -> GameJob:
    try:
        payload = GenerateGameRequest(
            prompt=prompt,
            difficulty=difficulty,
            audience=audience,
            session_length_sec=session_length_sec,
            character_prompt=character_prompt,
            obstacle_prompts=[line.strip() for line in obstacle_prompt_text.splitlines() if line.strip()],
            background_prompt=background_prompt,
            reference_images=await _store_uploads(request, "global", reference_images),
            character_reference_images=await _store_uploads(request, "character", character_images),
            obstacle_reference_images=await _store_uploads(request, "obstacle", obstacle_images),
            background_reference_images=await _store_uploads(request, "background", background_images),
        )
        return await _manager(request).create_job(payload, _base_url(request))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/games", response_model=list[GameJob])
async def list_games(request: Request) -> list[GameJob]:
    return await _manager(request).list_jobs()


@app.get("/games/{job_id}", response_model=GameJob)
async def get_game(job_id: str, request: Request) -> GameJob:
    job = await _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/games/{job_id}/manifest")
async def get_manifest(job_id: str, request: Request):
    job = await _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != GameJobStatus.DONE:
        raise HTTPException(status_code=409, detail="Manifest is not ready yet.")
    return await _manager(request).get_manifest(job_id)


@app.get("/games/play/{job_id}", response_class=HTMLResponse)
async def play_game(job_id: str, request: Request) -> HTMLResponse:
    job = await _manager(request).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.manifest_url is None:
        raise HTTPException(status_code=409, detail="Game is not ready yet.")
    html = _play_html(job.manifest_url, request.app.state.settings.phaser_cdn_url)
    return HTMLResponse(content=html)
