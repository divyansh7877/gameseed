from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class Difficulty(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class Audience(str, Enum):
    KIDS = "kids"
    TEEN = "teen"
    GENERAL = "general"


class GameJobStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING = "generating"
    ASSEMBLING = "assembling"
    DONE = "done"
    FAILED = "failed"


class ProviderKind(str, Enum):
    TRIPO = "tripo"
    BYTEPLUS = "byteplus"
    LOCAL = "local"


class AssetRole(str, Enum):
    CHARACTER = "character"
    OBSTACLE = "obstacle"
    COLLECTIBLE = "collectible"
    BACKGROUND = "background"


class AssetStatus(str, Enum):
    READY = "ready"
    FALLBACK = "fallback"
    FAILED = "failed"


class LayerName(str, Enum):
    FAR = "far"
    MID = "mid"
    NEAR = "near"


class GenerateGameRequest(BaseModel):
    prompt: str
    difficulty: Difficulty = Difficulty.NORMAL
    audience: Audience = Audience.GENERAL
    session_length_sec: int = 90
    reference_images: list[str] = Field(default_factory=list)
    character_prompt: str = ""
    obstacle_prompts: list[str] = Field(default_factory=list)
    background_prompt: str = ""
    character_reference_images: list[str] = Field(default_factory=list)
    obstacle_reference_images: list[str] = Field(default_factory=list)
    background_reference_images: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_request(self) -> "GenerateGameRequest":
        if len(self.prompt.strip().split()) < 3:
            raise ValueError("Prompt must contain at least three descriptive words.")
        if self.session_length_sec not in {60, 90, 120}:
            raise ValueError("session_length_sec must be one of 60, 90, or 120.")
        self.obstacle_prompts = [item.strip() for item in self.obstacle_prompts if item.strip()]
        return self


class RunnerSpec(BaseModel):
    theme: str
    art_style: str
    player_archetype: str
    obstacle_set: list[str]
    collectible_set: list[str]
    difficulty: Difficulty
    palette: list[str]
    session_length_sec: int
    audience: Audience
    title: str
    synopsis: str
    prompt_seed: int


class PlannedAsset(BaseModel):
    asset_id: str
    role: AssetRole
    provider: ProviderKind
    prompt: str
    variant: str
    layer: LayerName | None = None
    theme_hint: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetPlan(BaseModel):
    character: PlannedAsset
    obstacles: list[PlannedAsset]
    collectible: PlannedAsset
    backgrounds: list[PlannedAsset]

    @property
    def all_assets(self) -> list[PlannedAsset]:
        return [self.character, *self.obstacles, self.collectible, *self.backgrounds]


class AssetRuntime(BaseModel):
    asset_id: str
    role: AssetRole
    provider: ProviderKind
    status: AssetStatus
    label: str
    url: str
    width: int = 0
    height: int = 0
    fallback_reason: str | None = None
    lane: str | None = None
    collision_shape: str | None = None
    frames: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhysicsConfig(BaseModel):
    gravity_y: int
    jump_velocity: int
    ground_y: int
    player_start_x: int
    scroll_speed: int
    spawn_lead_px: int


class UIConfig(BaseModel):
    title: str
    subtitle: str
    audience_label: str


class SpawnEvent(BaseModel):
    time_ms: int
    asset_id: str
    lane: str
    kind: str


class BackgroundLayerConfig(BaseModel):
    asset_id: str
    url: str
    speed_multiplier: float
    depth: int
    alpha: float
    blend_tint: str
    layer: LayerName
    status: AssetStatus


class ValidationIssue(BaseModel):
    severity: str
    field: str
    message: str


class ManifestValidationReport(BaseModel):
    validator: str
    approved: bool
    coherence_score: float = 0.0
    summary: str = ""
    issues: list[ValidationIssue] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    applied_fixes: list[str] = Field(default_factory=list)


class GameManifest(BaseModel):
    game_id: str
    title: str
    prompt: str
    session_length_sec: int
    runner_spec: RunnerSpec
    ui: UIConfig
    physics: PhysicsConfig
    player: AssetRuntime
    obstacles: list[AssetRuntime]
    collectible: AssetRuntime
    backgrounds: list[BackgroundLayerConfig]
    spawn_table: list[SpawnEvent]
    sky_gradient: list[str]
    lane_positions: dict[str, int]
    score_to_win: int
    fallback_flags: dict[str, bool]
    validation: ManifestValidationReport | None = None


class GameJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    status: GameJobStatus = GameJobStatus.QUEUED
    request: GenerateGameRequest
    runner_spec: RunnerSpec | None = None
    asset_plan: AssetPlan | None = None
    manifest_url: str | None = None
    play_url: str | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    validation: ManifestValidationReport | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


class StoredCacheEntry(BaseModel):
    provider: ProviderKind
    cache_key: str
    files: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
