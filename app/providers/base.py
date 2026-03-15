from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models import AssetRuntime, PlannedAsset, RunnerSpec


@dataclass(slots=True)
class ProviderContext:
    job_id: str
    job_dir: Path
    base_url: str
    viewport: tuple[int, int]
    reference_images: list[str]


class ForegroundProvider(Protocol):
    async def generate(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext) -> AssetRuntime:
        ...


class BackgroundProvider(Protocol):
    async def generate(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext) -> AssetRuntime:
        ...

