import asyncio

from app.config import Settings
from app.manifest import build_manifest
from app.models import (
    AssetRole,
    AssetRuntime,
    AssetStatus,
    Audience,
    Difficulty,
    GenerateGameRequest,
    ProviderKind,
)
from app.planner import plan_runner
from app.validator import GeminiManifestValidator


class StubGeminiValidator(GeminiManifestValidator):
    def __init__(self) -> None:
        super().__init__(Settings(GEMINI_API_KEY="test-key"))

    async def _generate_json(self, prompt: str):
        return {
            "approved": True,
            "coherence_score": 0.77,
            "summary": "Mostly coherent.",
            "issues": [
                "The prompt specified 'orange neon' but the chosen palette leans purple.",
                {"severity": "warning", "field": "ui.subtitle", "message": "Subtitle is generic."},
            ],
            "recommendations": ["Tighten title wording."],
            "applied_fixes": ["Adjusted title."],
            "patches": {"title": "Bright Ruins Dash"},
        }


def test_validator_accepts_string_issues():
    spec = plan_runner(
        "make a vibrant runner",
        Difficulty.NORMAL,
        Audience.TEEN,
        120,
    )
    player = AssetRuntime(
        asset_id="player-main",
        role=AssetRole.CHARACTER,
        provider=ProviderKind.LOCAL,
        status=AssetStatus.FALLBACK,
        label="main",
        url="/files/player.png",
    )
    obstacles = [
        AssetRuntime(
            asset_id=f"obstacle-{index}",
            role=AssetRole.OBSTACLE,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.FALLBACK,
            label=f"obstacle-{index}",
            url=f"/files/obstacle-{index}.png",
            lane="ground",
        )
        for index in range(3)
    ]
    collectible = AssetRuntime(
        asset_id="collectible-main",
        role=AssetRole.COLLECTIBLE,
        provider=ProviderKind.LOCAL,
        status=AssetStatus.FALLBACK,
        label="collectible",
        url="/files/collectible.png",
    )
    backgrounds = [
        AssetRuntime(
            asset_id=f"background-{layer}",
            role=AssetRole.BACKGROUND,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.FALLBACK,
            label=layer,
            url=f"/files/{layer}.png",
            metadata={"layer": layer},
        )
        for layer in ("far", "mid", "near")
    ]
    manifest = build_manifest(
        game_id="job-1",
        prompt="make a vibrant runner",
        spec=spec,
        player=player,
        obstacles=obstacles,
        collectible=collectible,
        backgrounds=backgrounds,
    )
    request_body = GenerateGameRequest(
        prompt="make a vibrant runner",
        audience=Audience.TEEN,
        difficulty=Difficulty.NORMAL,
        session_length_sec=120,
    )
    validator = StubGeminiValidator()

    async def run_review():
        return await validator.review_manifest(request_body, manifest)

    updated_manifest, report, _ = asyncio.run(run_review())
    assert report is not None
    assert len(report.issues) == 2
    assert report.issues[0].message.startswith("The prompt specified")
    assert updated_manifest.title == "Bright Ruins Dash"
