from __future__ import annotations

import random

from app.models import (
    AssetRuntime,
    AssetStatus,
    BackgroundLayerConfig,
    Difficulty,
    GameManifest,
    LayerName,
    PhysicsConfig,
    RunnerSpec,
    SpawnEvent,
    UIConfig,
)


def difficulty_profile(difficulty: Difficulty) -> dict[str, int]:
    if difficulty == Difficulty.EASY:
        return {"gravity_y": 1550, "jump_velocity": -700, "scroll_speed": 320, "spawn_gap_min": 1800, "spawn_gap_max": 2600}
    if difficulty == Difficulty.HARD:
        return {"gravity_y": 1825, "jump_velocity": -780, "scroll_speed": 470, "spawn_gap_min": 1100, "spawn_gap_max": 1800}
    return {"gravity_y": 1680, "jump_velocity": -735, "scroll_speed": 390, "spawn_gap_min": 1450, "spawn_gap_max": 2150}


def build_manifest(
    *,
    game_id: str,
    prompt: str,
    spec: RunnerSpec,
    player: AssetRuntime,
    obstacles: list[AssetRuntime],
    collectible: AssetRuntime,
    backgrounds: list[AssetRuntime],
) -> GameManifest:
    profile = difficulty_profile(spec.difficulty)
    physics = PhysicsConfig(
        gravity_y=profile["gravity_y"],
        jump_velocity=profile["jump_velocity"],
        ground_y=610,
        player_start_x=220,
        scroll_speed=profile["scroll_speed"],
        spawn_lead_px=1400,
    )
    lane_positions = {"ground": 590, "air": 470, "bonus": 360}
    spawn_table = build_spawn_table(
        seed=spec.prompt_seed,
        session_length_sec=spec.session_length_sec,
        difficulty=spec.difficulty,
        obstacles=obstacles,
        collectible=collectible,
    )
    bg_configs = [
        BackgroundLayerConfig(
            asset_id=asset.asset_id,
            url=asset.url,
            speed_multiplier={LayerName.FAR: 0.18, LayerName.MID: 0.36, LayerName.NEAR: 0.62}[LayerName(asset.metadata["layer"])],
            depth=index,
            alpha={LayerName.FAR: 0.5, LayerName.MID: 0.42, LayerName.NEAR: 0.92}[LayerName(asset.metadata["layer"])],
            blend_tint=spec.palette[min(index + 1, len(spec.palette) - 1)],
            layer=LayerName(asset.metadata["layer"]),
            status=asset.status,
        )
        for index, asset in enumerate(sorted(backgrounds, key=lambda item: item.metadata["layer"]))
    ]
    fallback_flags = {
        "player": player.status != AssetStatus.READY,
        "obstacles": any(asset.status != AssetStatus.READY for asset in obstacles),
        "backgrounds": any(asset.status != AssetStatus.READY for asset in backgrounds),
        "collectible": collectible.status != AssetStatus.READY,
    }
    return GameManifest(
        game_id=game_id,
        title=spec.title,
        prompt=prompt,
        session_length_sec=spec.session_length_sec,
        runner_spec=spec,
        ui=UIConfig(
            title=spec.title,
            subtitle=f"{spec.player_archetype.title()} runner in a {spec.theme} world",
            audience_label=spec.audience.value,
        ),
        physics=physics,
        player=player,
        obstacles=obstacles,
        collectible=collectible,
        backgrounds=bg_configs,
        spawn_table=spawn_table,
        sky_gradient=[spec.palette[0], spec.palette[1], spec.palette[2]],
        lane_positions=lane_positions,
        score_to_win=max(8, spec.session_length_sec // 10),
        fallback_flags=fallback_flags,
    )


def build_spawn_table(
    *,
    seed: int,
    session_length_sec: int,
    difficulty: Difficulty,
    obstacles: list[AssetRuntime],
    collectible: AssetRuntime,
) -> list[SpawnEvent]:
    profile = difficulty_profile(difficulty)
    rng = random.Random(seed)
    events: list[SpawnEvent] = []
    current_ms = 1800
    end_ms = max(5000, session_length_sec * 1000 - 750)
    while current_ms < end_ms:
        obstacle = rng.choice(obstacles)
        lane = obstacle.lane or ("air" if "drone" in obstacle.label or "flying" in obstacle.label else "ground")
        events.append(SpawnEvent(time_ms=current_ms, asset_id=obstacle.asset_id, lane=lane, kind="obstacle"))
        if rng.random() < (0.38 if difficulty == Difficulty.EASY else 0.27 if difficulty == Difficulty.NORMAL else 0.16):
            events.append(
                SpawnEvent(
                    time_ms=current_ms + rng.randint(380, 640),
                    asset_id=collectible.asset_id,
                    lane="bonus" if lane == "ground" else "ground",
                    kind="collectible",
                )
            )
        current_ms += rng.randint(profile["spawn_gap_min"], profile["spawn_gap_max"])
    return sorted(events, key=lambda event: event.time_ms)
