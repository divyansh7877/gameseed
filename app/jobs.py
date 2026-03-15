from __future__ import annotations

import asyncio

from app.config import Settings
from app.manifest import build_manifest
from app.models import AssetRuntime, AssetStatus, GameJob, GameJobStatus, GameManifest, GenerateGameRequest
from app.planner import build_asset_plan, plan_runner
from app.providers.base import BackgroundProvider, ForegroundProvider, ProviderContext
from app.storage import GameStorage
from app.validator import ManifestValidator


class GameJobManager:
    def __init__(
        self,
        settings: Settings,
        storage: GameStorage,
        foreground_provider: ForegroundProvider,
        background_provider: BackgroundProvider,
        validator: ManifestValidator | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.foreground_provider = foreground_provider
        self.background_provider = background_provider
        self.validator = validator
        self.jobs = self.storage.load_all_jobs()
        self._lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def create_job(self, request_body: GenerateGameRequest, base_url: str) -> GameJob:
        job = GameJob(request=request_body)
        job.play_url = f"{base_url.rstrip('/')}/games/play/{job.job_id}"
        async with self._lock:
            self._persist(job)
        self.storage.write_named_payload(job.job_id, "request.json", request_body.model_dump(mode="json"))
        self._tasks[job.job_id] = asyncio.create_task(self._process_job(job.job_id, request_body, base_url))
        return job

    async def get_job(self, job_id: str) -> GameJob | None:
        async with self._lock:
            return self.jobs.get(job_id)

    async def list_jobs(self, limit: int = 20) -> list[GameJob]:
        async with self._lock:
            return sorted(self.jobs.values(), key=lambda job: job.updated_at, reverse=True)[:limit]

    async def get_manifest(self, job_id: str) -> GameManifest:
        path = self.storage.job_dir(job_id) / "manifest.json"
        return GameManifest.model_validate_json(path.read_text(encoding="utf-8"))

    async def wait_for_job(self, job_id: str, timeout: float = 10.0) -> GameJob:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            job = await self.get_job(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in {GameJobStatus.DONE, GameJobStatus.FAILED}:
                return job
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for game job {job_id}.")
            await asyncio.sleep(0.05)

    async def close(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    async def _process_job(self, job_id: str, request_body: GenerateGameRequest, base_url: str) -> None:
        try:
            await self._set_status(job_id, GameJobStatus.PLANNING)
            spec = plan_runner(
                request_body.prompt,
                request_body.difficulty,
                request_body.audience,
                request_body.session_length_sec,
            )
            if self.validator is not None:
                spec, raw_spec_review = await self.validator.refine_runner_spec(request_body, spec)
                if raw_spec_review is not None:
                    self.storage.write_named_payload(job_id, "gemini_spec_review.json", raw_spec_review)
            asset_plan = build_asset_plan(spec, request_body)
            self.storage.write_named_payload(job_id, "runner_spec.json", spec.model_dump(mode="json"))
            self.storage.write_named_payload(job_id, "asset_plan.json", asset_plan.model_dump(mode="json"))

            async with self._lock:
                job = self.jobs[job_id]
                job.runner_spec = spec
                job.asset_plan = asset_plan
                self._persist(job)

            await self._set_status(job_id, GameJobStatus.GENERATING)
            context = ProviderContext(
                job_id=job_id,
                job_dir=self.storage.job_dir(job_id),
                base_url=base_url,
                viewport=(self.settings.default_viewport_width, self.settings.default_viewport_height),
                reference_images=request_body.reference_images,
            )
            fg_tasks = [
                self.foreground_provider.generate(asset, spec, context)
                for asset in [asset_plan.character, *asset_plan.obstacles, asset_plan.collectible]
            ]
            bg_tasks = [self.background_provider.generate(asset, spec, context) for asset in asset_plan.backgrounds]
            fg_results = await asyncio.gather(*fg_tasks)
            bg_results = await asyncio.gather(*bg_tasks)

            player, *rest = fg_results
            obstacles = rest[:3]
            collectible = rest[3]
            playable_obstacles = sum(1 for asset in obstacles if asset.status != AssetStatus.FAILED)
            playable_backgrounds = sum(1 for asset in bg_results if asset.status != AssetStatus.FAILED)
            if player.status == AssetStatus.FAILED or playable_obstacles < 2 or playable_backgrounds < 1:
                raise RuntimeError("Game generation did not produce enough playable assets.")

            await self._set_status(job_id, GameJobStatus.ASSEMBLING)
            manifest = build_manifest(
                game_id=job_id,
                prompt=request_body.prompt,
                spec=spec,
                player=player,
                obstacles=obstacles,
                collectible=collectible,
                backgrounds=bg_results,
            )
            if self.validator is not None:
                manifest, validation_report, raw_manifest_review = await self.validator.review_manifest(request_body, manifest)
                if raw_manifest_review is not None:
                    self.storage.write_named_payload(job_id, "gemini_manifest_review.json", raw_manifest_review)
                if validation_report is not None:
                    async with self._lock:
                        job = self.jobs[job_id]
                        job.validation = validation_report
                        self._persist(job)
            manifest_path = self.storage.job_dir(job_id) / "manifest.json"
            self.storage.write_json(manifest_path, manifest.model_dump(mode="json"))

            async with self._lock:
                job = self.jobs[job_id]
                job.status = GameJobStatus.DONE
                job.manifest_url = self.storage.public_url(base_url, manifest_path)
                job.validation = manifest.validation
                self._persist(job)
        except Exception as exc:
            async with self._lock:
                job = self.jobs[job_id]
                job.status = GameJobStatus.FAILED
                job.error = str(exc)
                self._persist(job)

    async def _set_status(self, job_id: str, status: GameJobStatus) -> None:
        async with self._lock:
            job = self.jobs[job_id]
            job.status = status
            self._persist(job)

    def _persist(self, job: GameJob) -> None:
        job.touch()
        self.jobs[job.job_id] = job
        self.storage.save_job(job)
