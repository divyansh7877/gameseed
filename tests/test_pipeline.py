import asyncio

from app.config import Settings
from app.image_utils import write_placeholder_background, write_placeholder_sprite
from app.jobs import GameJobManager
from app.models import (
    AssetRole,
    AssetRuntime,
    AssetStatus,
    GenerateGameRequest,
    ManifestValidationReport,
    ProviderKind,
)
from app.providers.base import ProviderContext
from app.storage import GameStorage


class FakeForegroundProvider:
    async def generate(self, planned_asset, spec, context: ProviderContext) -> AssetRuntime:
        destination = context.job_dir / "assets" / f"{planned_asset.asset_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_placeholder_sprite(destination, planned_asset.variant, spec.palette)
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.READY if planned_asset.role != AssetRole.COLLECTIBLE else AssetStatus.FALLBACK,
            label=planned_asset.variant,
            url=f"{context.base_url}/files/games/{context.job_id}/assets/{planned_asset.asset_id}.png",
            width=256,
            height=256,
            lane=planned_asset.metadata.get("lane"),
            collision_shape="rectangle",
            fallback_reason=None if planned_asset.role != AssetRole.COLLECTIBLE else "placeholder collectible",
        )


class FakeBackgroundProvider:
    async def generate(self, planned_asset, spec, context: ProviderContext) -> AssetRuntime:
        destination = context.job_dir / "assets" / f"{planned_asset.asset_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_placeholder_background(destination, planned_asset.layer, spec.palette, (context.viewport[0] * 2, context.viewport[1]))
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.FALLBACK,
            label=planned_asset.variant,
            url=f"{context.base_url}/files/games/{context.job_id}/assets/{planned_asset.asset_id}.png",
            width=context.viewport[0] * 2,
            height=context.viewport[1],
            fallback_reason="background fallback",
            metadata={"layer": planned_asset.layer.value},
        )


class FakeValidator:
    async def refine_runner_spec(self, request_body, initial_spec):
        refined = initial_spec.model_copy(update={"title": "Validated Dash", "theme": "cyberpunk"})
        return refined, {"approved": True, "runner_spec": refined.model_dump(mode="json"), "applied_fixes": ["Adjusted title and theme"]}

    async def review_manifest(self, request_body, draft_manifest):
        patched = draft_manifest.model_copy(deep=True)
        patched.title = "Validated Dash"
        patched.ui.title = "Validated Dash"
        patched.ui.subtitle = "Validated by Gemini layer"
        report = ManifestValidationReport(
            validator="gemini",
            approved=True,
            coherence_score=0.91,
            summary="Looks coherent after text repair.",
            applied_fixes=["Patched title", "Patched subtitle"],
        )
        patched.validation = report
        return patched, report, {"approved": True, "patches": {"title": "Validated Dash", "ui_subtitle": "Validated by Gemini layer"}}


def test_pipeline_generates_manifest_with_fallbacks(tmp_path):
    settings = Settings(
        PUBLIC_BASE_URL="http://127.0.0.1:8000",
        DATA_ROOT=tmp_path,
    )
    storage = GameStorage(settings.data_root)
    manager = GameJobManager(
        settings=settings,
        storage=storage,
        foreground_provider=FakeForegroundProvider(),
        background_provider=FakeBackgroundProvider(),
    )

    async def run_job():
        job = await manager.create_job(
            GenerateGameRequest(
                prompt="cyberpunk neon courier running across rooftop billboards",
                session_length_sec=60,
            ),
            "http://127.0.0.1:8000",
        )
        final_job = await manager.wait_for_job(job.job_id)
        manifest = await manager.get_manifest(job.job_id)
        await manager.close()
        return final_job, manifest

    final_job, manifest = asyncio.run(run_job())
    assert final_job.status.value == "done"
    assert manifest.player.asset_id == "player-main"
    assert len(manifest.obstacles) == 3
    assert len(manifest.backgrounds) == 3
    assert manifest.fallback_flags["backgrounds"] is True
    assert manifest.spawn_table


def test_pipeline_applies_validator_refinement(tmp_path):
    settings = Settings(
        PUBLIC_BASE_URL="http://127.0.0.1:8000",
        DATA_ROOT=tmp_path,
        ENABLE_GEMINI_VALIDATION=False,
    )
    storage = GameStorage(settings.data_root)
    manager = GameJobManager(
        settings=settings,
        storage=storage,
        foreground_provider=FakeForegroundProvider(),
        background_provider=FakeBackgroundProvider(),
        validator=FakeValidator(),
    )

    async def run_job():
        job = await manager.create_job(
            GenerateGameRequest(
                prompt="make a vibrant runner",
                audience="teen",
                session_length_sec=120,
            ),
            "http://127.0.0.1:8000",
        )
        final_job = await manager.wait_for_job(job.job_id)
        manifest = await manager.get_manifest(job.job_id)
        await manager.close()
        return final_job, manifest

    final_job, manifest = asyncio.run(run_job())
    assert final_job.status.value == "done"
    assert manifest.title == "Validated Dash"
    assert manifest.ui.subtitle == "Validated by Gemini layer"
    assert manifest.validation is not None
    assert manifest.validation.approved is True
