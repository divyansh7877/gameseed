from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
from PIL import Image

from app.config import Settings
from app.image_utils import load_image_bytes, make_repeat_safe, postprocess_background, write_placeholder_background
from app.models import AssetRuntime, AssetStatus, LayerName, PlannedAsset, ProviderKind, RunnerSpec, StoredCacheEntry
from app.providers.base import ProviderContext
from app.storage import GameStorage

BACKGROUND_PROCESSING_VERSION = "v2"


class BytePlusBackgroundProvider:
    def __init__(self, settings: Settings, storage: GameStorage) -> None:
        self.settings = settings
        self.storage = storage

    async def generate(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext) -> AssetRuntime:
        planned_images = list(planned_asset.metadata.get("images", []))
        cache_key = self._cache_key(planned_asset, spec, planned_images or context.reference_images)
        cached = self.storage.load_cache_entry(ProviderKind.BYTEPLUS, cache_key)
        if cached is not None:
            return self._materialize_cached_runtime(planned_asset, cached, context, status=AssetStatus.READY)

        if self.settings.ark_api_key:
            try:
                runtime = await self._generate_remote(planned_asset, spec, context, cache_key)
                return runtime
            except Exception:
                theme_runtime = self._try_theme_cache(planned_asset, spec, context)
                if theme_runtime is not None:
                    return theme_runtime

        return self._write_placeholder(planned_asset, spec, context, "BytePlus generation unavailable.")

    def _cache_key(self, planned_asset: PlannedAsset, spec: RunnerSpec, reference_images: list[str]) -> str:
        payload = {
            "prompt": planned_asset.prompt,
            "theme": spec.theme,
            "layer": planned_asset.layer.value if planned_asset.layer else "",
            "model": self.settings.byteplus_model,
            "refs": reference_images,
            "processing": BACKGROUND_PROCESSING_VERSION,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    async def _generate_remote(
        self,
        planned_asset: PlannedAsset,
        spec: RunnerSpec,
        context: ProviderContext,
        cache_key: str,
    ) -> AssetRuntime:
        headers = {"Authorization": f"Bearer {self.settings.ark_api_key}"}
        prompt = (
            f"{planned_asset.prompt}. {self._layer_instruction(planned_asset.layer or LayerName.FAR)}. Art style: {spec.art_style}. "
            f"Theme colors: {', '.join(spec.palette[:4])}. "
            "This layer must work as a scrolling 2D backdrop."
        )
        request_body = {
            "model": self.settings.byteplus_model,
            "prompt": prompt,
            "size": self.settings.byteplus_image_size,
        }
        reference_images = list(planned_asset.metadata.get("images", [])) or context.reference_images
        if reference_images:
            request_body["metadata"] = {"reference_images": reference_images}

        async with httpx.AsyncClient(
            base_url=self.settings.byteplus_base_url.rstrip("/"),
            timeout=self.settings.byteplus_timeout_seconds,
            headers=headers,
        ) as client:
            response = await client.post("/images/generations", json=request_body)
            response.raise_for_status()
            payload = response.json()
        self.storage.write_named_payload(context.job_id, f"byteplus_{planned_asset.asset_id}.json", payload)

        image = self._extract_image(payload)
        processed = postprocess_background(image, planned_asset.layer or LayerName.FAR, spec.palette, context.viewport)
        tiled = make_repeat_safe(processed, context.viewport)
        destination = self.storage.job_assets_dir(context.job_id) / f"{planned_asset.asset_id}.png"
        tiled.save(destination)

        cache_dir = self.storage.cache_dir(ProviderKind.BYTEPLUS, cache_key)
        cache_destination = cache_dir / destination.name
        cache_destination.parent.mkdir(parents=True, exist_ok=True)
        tiled.save(cache_destination)
        theme_dir = self.storage.cached_theme_dir(
            ProviderKind.BYTEPLUS,
            f"{spec.theme}-{planned_asset.layer.value}-{BACKGROUND_PROCESSING_VERSION}",
        )
        tiled.save(theme_dir / destination.name)
        self.storage.save_cache_entry(
            StoredCacheEntry(
                provider=ProviderKind.BYTEPLUS,
                cache_key=cache_key,
                files={"main": destination.name},
                metadata={"layer": planned_asset.layer.value, "theme": spec.theme},
            )
        )
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.BYTEPLUS,
            status=AssetStatus.READY,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, destination),
            width=tiled.width,
            height=tiled.height,
            metadata={"layer": planned_asset.layer.value},
        )

    def _try_theme_cache(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext) -> AssetRuntime | None:
        theme_dir = self.storage.cached_theme_dir(
            ProviderKind.BYTEPLUS,
            f"{spec.theme}-{planned_asset.layer.value}-{BACKGROUND_PROCESSING_VERSION}",
        )
        candidates = sorted(theme_dir.glob("*.png"))
        if not candidates:
            return None
        copied = self.storage.copy_into_job(candidates[-1], context.job_id, f"{planned_asset.asset_id}.png")
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.BYTEPLUS,
            status=AssetStatus.FALLBACK,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, copied),
            width=context.viewport[0] * 2,
            height=context.viewport[1],
            fallback_reason="Reused cached theme background.",
            metadata={"layer": planned_asset.layer.value},
        )

    def _materialize_cached_runtime(
        self,
        planned_asset: PlannedAsset,
        cached: StoredCacheEntry,
        context: ProviderContext,
        *,
        status: AssetStatus,
    ) -> AssetRuntime:
        cache_dir = self.storage.cache_dir(ProviderKind.BYTEPLUS, cached.cache_key)
        source = cache_dir / cached.files["main"]
        copied = self.storage.copy_into_job(source, context.job_id, f"{planned_asset.asset_id}.png")
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.BYTEPLUS,
            status=status,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, copied),
            width=context.viewport[0] * 2,
            height=context.viewport[1],
            metadata={"layer": planned_asset.layer.value},
        )

    def _write_placeholder(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext, reason: str) -> AssetRuntime:
        destination = self.storage.job_assets_dir(context.job_id) / f"{planned_asset.asset_id}.png"
        width, height = write_placeholder_background(destination, planned_asset.layer or LayerName.FAR, spec.palette, (context.viewport[0] * 2, context.viewport[1]))
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.LOCAL,
            status=AssetStatus.FALLBACK,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, destination),
            width=width,
            height=height,
            fallback_reason=reason,
            metadata={"layer": planned_asset.layer.value},
        )

    def _extract_image(self, payload: dict) -> Image.Image:
        data = payload.get("data") or []
        if not data:
            raise RuntimeError("BytePlus image response did not contain data.")
        image_ref = data[0]
        if "b64_json" in image_ref:
            return load_image_bytes(base64.b64decode(image_ref["b64_json"]))
        if "url" in image_ref:
            response = httpx.get(image_ref["url"], timeout=self.settings.byteplus_timeout_seconds)
            response.raise_for_status()
            return load_image_bytes(response.content)
        raise RuntimeError("BytePlus image response did not contain a supported image payload.")

    @staticmethod
    def _layer_instruction(layer: LayerName) -> str:
        if layer == LayerName.FAR:
            return "Render only distant atmospheric skyline and horizon masses, low detail, no foreground objects"
        if layer == LayerName.MID:
            return "Render midground structures and large shapes only, moderate contrast, no hero or near-camera objects"
        return "Render only sparse near-foreground silhouettes anchored to the lower frame, high contrast, no full-scene background"
