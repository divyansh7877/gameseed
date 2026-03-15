from __future__ import annotations

import hashlib
import re

from app.models import (
    AssetPlan,
    AssetRole,
    Audience,
    Difficulty,
    GenerateGameRequest,
    LayerName,
    PlannedAsset,
    ProviderKind,
    RunnerSpec,
)


THEME_LIBRARY: dict[str, dict[str, list[str] | str]] = {
    "cyberpunk": {
        "palette": ["#0b1021", "#1a2a6c", "#00d1ff", "#ff4fd8", "#ffe66d"],
        "obstacles": ["broken neon barrier", "hover drone hazard", "spark gate arch"],
        "collectible": "plasma battery cell",
        "style": "stylized neon arcade runner art, bold silhouette, crisp edges",
    },
    "jungle": {
        "palette": ["#0f3d24", "#1f6f43", "#73c66d", "#f4d35e", "#f9f7d9"],
        "obstacles": ["vine snare log", "stone idol gate", "swinging branch trap"],
        "collectible": "sun fruit token",
        "style": "playful jungle adventure art, soft shapes, bright readable colors",
    },
    "space": {
        "palette": ["#090b1a", "#273469", "#5c7aea", "#9ee493", "#f7f7ff"],
        "obstacles": ["meteor shard cluster", "laser cargo crate", "orbit ring gate"],
        "collectible": "starlight crystal",
        "style": "vivid sci-fi side runner art, clean silhouette, glossy highlights",
    },
    "desert": {
        "palette": ["#412722", "#8c5e34", "#d89d4a", "#f1d6a2", "#87c38f"],
        "obstacles": ["sandstone pillar", "scarab cart", "wind gate totem"],
        "collectible": "sun coin",
        "style": "storybook desert runner art, warm tones, readable shapes",
    },
    "winter": {
        "palette": ["#102542", "#35605a", "#4ea5d9", "#bce7fd", "#f4faff"],
        "obstacles": ["ice shard fence", "snowdrift boulder", "frost gate"],
        "collectible": "aurora snowflake",
        "style": "cozy winter runner art, soft contrast, clean silhouette",
    },
    "ruins": {
        "palette": ["#1f1d36", "#3f3351", "#864879", "#e9a6a6", "#f9f9f9"],
        "obstacles": ["cracked temple wall", "floating relic eye", "collapsed archway"],
        "collectible": "ancient glyph orb",
        "style": "mystic ruins runner art, bold shapes, magical highlights",
    },
}

PLAYER_ARCHETYPES = [
    "courier",
    "explorer",
    "ninja",
    "robot",
    "wizard",
    "skater",
    "ranger",
    "pilot",
]

NON_RUNNER_HINTS = ("rpg", "strategy", "farm", "sim", "chess", "city builder", "turn-based")


def _normalize_words(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _choose_theme(prompt: str) -> str:
    lowered = _normalize_words(prompt)
    for theme in THEME_LIBRARY:
        if theme in lowered:
            return theme
    if any(word in lowered for word in ("neon", "future", "robot", "drone", "cyber")):
        return "cyberpunk"
    if any(word in lowered for word in ("jungle", "vine", "temple", "explorer")):
        return "jungle"
    if any(word in lowered for word in ("space", "star", "galaxy", "cosmic")):
        return "space"
    if any(word in lowered for word in ("desert", "sand", "cactus")):
        return "desert"
    if any(word in lowered for word in ("snow", "ice", "winter", "frost")):
        return "winter"
    return "ruins"


def _choose_player(prompt: str, audience: Audience) -> str:
    lowered = _normalize_words(prompt)
    for archetype in PLAYER_ARCHETYPES:
        if archetype in lowered:
            return archetype
    if "kid" in lowered or audience == Audience.KIDS:
        return "young explorer"
    if "robot" in lowered or "android" in lowered:
        return "robot courier"
    return "runner hero"


def _theme_data(theme: str) -> dict[str, list[str] | str]:
    return THEME_LIBRARY.get(theme, THEME_LIBRARY["ruins"])


def _compose_character_prompt(user_prompt: str, spec: RunnerSpec) -> str:
    cleaned = user_prompt.strip()
    if cleaned:
        return (
            f"{cleaned}, playable runner character for a {spec.theme} world, "
            f"side-view readable silhouette, {spec.art_style}"
        )
    return (
        f"{spec.player_archetype} in a {spec.theme} endless runner, "
        f"side view, readable silhouette, {spec.art_style}"
    )


def _compose_obstacle_prompt(user_prompt: str, variant: str, spec: RunnerSpec) -> str:
    cleaned = user_prompt.strip()
    subject = cleaned if cleaned else variant
    return (
        f"{subject}, obstacle for a {spec.theme} endless runner, "
        f"side view, readable silhouette, {spec.art_style}"
    )


def _compose_collectible_prompt(variant: str, spec: RunnerSpec) -> str:
    return (
        f"{variant}, collectible pickup for a {spec.theme} endless runner, "
        f"side view, bright pickup silhouette, {spec.art_style}"
    )


def _compose_background_prompt(prefix: str, layer: LayerName, spec: RunnerSpec) -> str:
    cleaned = prefix.strip()
    scene_prefix = cleaned if cleaned else f"{spec.theme} endless runner background scene"
    return (
        f"{scene_prefix}, {layer.value} parallax layer, "
        "2D side-scrolling scenery, no hero subject, wide composition, "
        "strong silhouette separation, empty horizontal breathing room"
    )


def plan_runner(prompt: str, difficulty: Difficulty, audience: Audience, session_length_sec: int) -> RunnerSpec:
    normalized = _normalize_words(prompt)
    theme = _choose_theme(prompt)
    data = _theme_data(theme)
    style = str(data["style"])
    if audience == Audience.KIDS:
        style = f"{style}, friendly shapes, gentle intensity"
    elif audience == Audience.TEEN:
        style = f"{style}, slightly bolder action energy"
    player_archetype = _choose_player(prompt, audience)
    synopsis = normalized
    if any(hint in normalized for hint in NON_RUNNER_HINTS):
        synopsis = f"{normalized}. Reframed as a fast side-view endless runner adventure."
    title = f"{theme.title()} Dash"
    seed_hex = hashlib.sha256(f"{normalized}:{difficulty.value}:{audience.value}".encode("utf-8")).hexdigest()[:8]
    return RunnerSpec(
        theme=theme,
        art_style=style,
        player_archetype=player_archetype,
        obstacle_set=list(data["obstacles"]),
        collectible_set=[str(data["collectible"])],
        difficulty=difficulty,
        palette=list(data["palette"]),
        session_length_sec=session_length_sec,
        audience=audience,
        title=title,
        synopsis=synopsis,
        prompt_seed=int(seed_hex, 16),
    )


def build_asset_plan(spec: RunnerSpec, request: GenerateGameRequest | None = None) -> AssetPlan:
    request = request or GenerateGameRequest(prompt=spec.synopsis, difficulty=spec.difficulty, audience=spec.audience, session_length_sec=spec.session_length_sec)
    global_reference_images = list(request.reference_images)
    character_images = [*request.character_reference_images, *global_reference_images]
    obstacle_images = [*request.obstacle_reference_images, *global_reference_images]
    background_images = [*request.background_reference_images, *global_reference_images]
    character_prompt = _compose_character_prompt(request.character_prompt, spec)
    character = PlannedAsset(
        asset_id="player-main",
        role=AssetRole.CHARACTER,
        provider=ProviderKind.TRIPO,
        variant="main",
        theme_hint=spec.theme,
        prompt=character_prompt,
        metadata={"images": character_images},
    )
    obstacle_prompt_overrides = request.obstacle_prompts[:3]
    obstacles = [
        PlannedAsset(
            asset_id=f"obstacle-{index + 1}",
            role=AssetRole.OBSTACLE,
            provider=ProviderKind.TRIPO,
            variant=variant,
            theme_hint=spec.theme,
            prompt=_compose_obstacle_prompt(
                obstacle_prompt_overrides[index] if index < len(obstacle_prompt_overrides) else "",
                variant,
                spec,
            ),
            metadata={
                "lane": "ground" if index != 1 else "air",
                "images": obstacle_images,
            },
        )
        for index, variant in enumerate(spec.obstacle_set[:3])
    ]
    collectible = PlannedAsset(
        asset_id="collectible-main",
        role=AssetRole.COLLECTIBLE,
        provider=ProviderKind.TRIPO,
        variant=spec.collectible_set[0],
        theme_hint=spec.theme,
        prompt=_compose_collectible_prompt(spec.collectible_set[0], spec),
        metadata={"lane": "air", "images": obstacle_images},
    )
    background_prompt_prefix = request.background_prompt.strip()
    backgrounds = [
        PlannedAsset(
            asset_id=f"background-{layer.value}",
            role=AssetRole.BACKGROUND,
            provider=ProviderKind.BYTEPLUS,
            variant=f"{layer.value} layer",
            layer=layer,
            theme_hint=spec.theme,
            prompt=_compose_background_prompt(background_prompt_prefix, layer, spec),
            metadata={"images": background_images},
        )
        for layer in (LayerName.FAR, LayerName.MID, LayerName.NEAR)
    ]
    return AssetPlan(
        character=character,
        obstacles=obstacles,
        collectible=collectible,
        backgrounds=backgrounds,
    )
