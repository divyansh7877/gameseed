from app.manifest import build_manifest
from app.models import AssetRole, AssetRuntime, AssetStatus, Audience, Difficulty, GenerateGameRequest, ProviderKind
from app.planner import build_asset_plan, plan_runner


def test_planner_infers_theme_and_coerces_non_runner_prompt():
    spec = plan_runner(
        "make a cyberpunk strategy game about a neon courier on rooftops",
        Difficulty.NORMAL,
        audience=Audience.GENERAL,
        session_length_sec=90,
    )
    assert spec.theme == "cyberpunk"
    assert "runner" in spec.synopsis
    assert spec.player_archetype in {"courier", "runner hero"}


def test_manifest_difficulty_changes_scroll_speed():
    easy_spec = plan_runner(
        "cute jungle explorer sprinting through vines",
        Difficulty.EASY,
        audience=Audience.KIDS,
        session_length_sec=60,
    )
    hard_spec = plan_runner(
        "cute jungle explorer sprinting through vines",
        Difficulty.HARD,
        audience=Audience.KIDS,
        session_length_sec=60,
    )
    player = AssetRuntime(
        asset_id="player-main",
        role=AssetRole.CHARACTER,
        provider=ProviderKind.LOCAL,
        status=AssetStatus.FALLBACK,
        label="player",
        url="/files/player.png",
    )
    obstacles = [
        AssetRuntime(
            asset_id=f"obstacle-{index}",
            role=AssetRole.OBSTACLE,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.FALLBACK,
            label="obstacle",
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
    easy_manifest = build_manifest(
        game_id="easy",
        prompt="runner",
        spec=easy_spec,
        player=player,
        obstacles=obstacles,
        collectible=collectible,
        backgrounds=backgrounds,
    )
    hard_manifest = build_manifest(
        game_id="hard",
        prompt="runner",
        spec=hard_spec,
        player=player,
        obstacles=obstacles,
        collectible=collectible,
        backgrounds=backgrounds,
    )
    assert easy_manifest.physics.scroll_speed < hard_manifest.physics.scroll_speed
    assert len(hard_manifest.spawn_table) >= len(easy_manifest.spawn_table)


def test_asset_plan_enriches_short_override_prompts():
    spec = plan_runner(
        "vibrant run game",
        Difficulty.NORMAL,
        Audience.GENERAL,
        90,
    )
    asset_plan = build_asset_plan(
        spec,
        GenerateGameRequest(
            prompt="vibrant run game",
            character_prompt="red short blob",
            obstacle_prompts=["blue bottle"],
            background_prompt="pink tree",
        ),
    )
    assert "playable runner character" in asset_plan.character.prompt
    assert f"{spec.theme} world" in asset_plan.character.prompt
    assert f"obstacle for a {spec.theme} endless runner" in asset_plan.obstacles[0].prompt
    assert "pink tree" in asset_plan.backgrounds[0].prompt
