from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.image_utils import write_placeholder_sprite
from app.models import AssetRole, AssetRuntime, AssetStatus, PlannedAsset, ProviderKind, RunnerSpec, StoredCacheEntry
from app.providers.base import ProviderContext
from app.storage import GameStorage


class TripoForegroundProvider:
    def __init__(self, settings: Settings, storage: GameStorage) -> None:
        self.settings = settings
        self.storage = storage

    async def generate(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext) -> AssetRuntime:
        payload = {
            "asset_type": "character" if planned_asset.role == AssetRole.CHARACTER else "obstacle",
            "prompt": planned_asset.prompt,
            "theme": spec.theme,
            "variant": planned_asset.variant,
        }
        cache_key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        cached = self.storage.load_cache_entry(ProviderKind.TRIPO, cache_key)
        if cached is not None:
            return self._materialize_cached_runtime(planned_asset, cached, context, status=AssetStatus.READY)

        if not self.settings.tripo_asset_base_url:
            return self._write_placeholder(planned_asset, spec, context, "TRIPO_ASSET_BASE_URL is not configured.")

        try:
            runtime = await self._generate_from_service(planned_asset, spec, context, cache_key)
            return runtime
        except Exception as exc:
            return self._write_placeholder(planned_asset, spec, context, str(exc))

    async def _generate_from_service(
        self,
        planned_asset: PlannedAsset,
        spec: RunnerSpec,
        context: ProviderContext,
        cache_key: str,
    ) -> AssetRuntime:
        images = list(planned_asset.metadata.get("images", []))
        if images:
            input_mode = "image_plus_text" if planned_asset.prompt.strip() else "image"
        else:
            input_mode = "text"
        request_body = {
            "asset_type": "character" if planned_asset.role == AssetRole.CHARACTER else "obstacle",
            "input_mode": input_mode,
            "prompt": planned_asset.prompt,
            "images": images,
            "style_prompt": spec.art_style,
            "theme_tags": [spec.theme],
            "output_profile": "runner_v1",
            # The Phaser runtime only uses still sprite outputs right now, so skip rigging/retargeting.
            "need_animation": False,
            "views": ["side", "front"] if planned_asset.role == AssetRole.CHARACTER else ["side"],
            "transparent_bg": True,
        }
        async with httpx.AsyncClient(timeout=self.settings.tripo_timeout_seconds) as client:
            response = await client.post(f"{self.settings.tripo_asset_base_url.rstrip('/')}/artifacts/generate", json=request_body)
            response.raise_for_status()
            created = response.json()
            job_id = created["job_id"]
            final_payload = await self._poll_until_done(client, job_id)
            self.storage.write_named_payload(context.job_id, f"tripo_{planned_asset.asset_id}.json", final_payload)

            downloaded_files: dict[str, str] = {}
            sprite_urls = final_payload.get("sprite_urls", {})
            primary_remote = self._select_primary_remote_url(planned_asset, sprite_urls)
            primary_path = await self._download_remote(client, primary_remote, context, f"{planned_asset.asset_id}.png")
            downloaded_files["main"] = primary_path.name

            frames: dict[str, str] = {}
            if planned_asset.role == AssetRole.CHARACTER:
                for name in ("side_idle", "side_run_1", "front_portrait"):
                    remote = sprite_urls.get(name)
                    if not remote:
                        continue
                    filename = f"{planned_asset.asset_id}-{name}.png"
                    local = await self._download_remote(client, remote, context, filename)
                    key = "run" if name == "side_run_1" else "idle" if name == "side_idle" else "portrait"
                    frames[key] = self.storage.public_url(context.base_url, local)
                    downloaded_files[key] = local.name

        cache_dir = self.storage.cache_dir(ProviderKind.TRIPO, cache_key)
        for filename in downloaded_files.values():
            source = self.storage.job_assets_dir(context.job_id) / filename
            destination = cache_dir / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        self.storage.save_cache_entry(
            StoredCacheEntry(
                provider=ProviderKind.TRIPO,
                cache_key=cache_key,
                files=downloaded_files,
                metadata={
                    "frames": frames,
                    "raw_job": final_payload,
                    "width": int(final_payload.get("metadata", {}).get("bounding_box_hint", {}).get("width", 0)),
                    "height": int(final_payload.get("metadata", {}).get("bounding_box_hint", {}).get("height", 0)),
                    "collision_shape": final_payload.get("metadata", {}).get("collision_mask_suggestion"),
                },
            )
        )
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.TRIPO,
            status=AssetStatus.READY,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, primary_path),
            width=int(final_payload.get("metadata", {}).get("bounding_box_hint", {}).get("width", 0)),
            height=int(final_payload.get("metadata", {}).get("bounding_box_hint", {}).get("height", 0)),
            lane=planned_asset.metadata.get("lane"),
            collision_shape=final_payload.get("metadata", {}).get("collision_mask_suggestion"),
            frames=frames,
            metadata={"provider_job_id": job_id},
        )

    async def _poll_until_done(self, client: httpx.AsyncClient, provider_job_id: str) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + self.settings.tripo_timeout_seconds
        while True:
            response = await client.get(f"{self.settings.tripo_asset_base_url.rstrip('/')}/artifacts/{provider_job_id}")
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status")
            if status == "done":
                return payload
            if status == "failed":
                raise RuntimeError(payload.get("error") or "Tripo generation failed.")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Timed out waiting for Tripo artifact generation.")
            await asyncio.sleep(self.settings.tripo_poll_interval_seconds)

    async def _download_remote(
        self,
        client: httpx.AsyncClient,
        remote_url: str,
        context: ProviderContext,
        filename: str,
    ) -> Path:
        response = await client.get(remote_url)
        response.raise_for_status()
        destination = self.storage.job_assets_dir(context.job_id) / filename
        destination.write_bytes(response.content)
        return destination

    def _select_primary_remote_url(self, planned_asset: PlannedAsset, sprite_urls: dict[str, str]) -> str:
        if planned_asset.role == AssetRole.CHARACTER:
            for key in ("side_idle", "side_run_1", "front_portrait"):
                if key in sprite_urls:
                    return sprite_urls[key]
        if "side" in sprite_urls:
            return sprite_urls["side"]
        if sprite_urls:
            return next(iter(sprite_urls.values()))
        raise RuntimeError("Tripo job completed without usable sprite outputs.")

    def _materialize_cached_runtime(
        self,
        planned_asset: PlannedAsset,
        cached: StoredCacheEntry,
        context: ProviderContext,
        *,
        status: AssetStatus,
    ) -> AssetRuntime:
        cache_dir = self.storage.cache_dir(ProviderKind.TRIPO, cached.cache_key)
        files = cached.files
        main_source = cache_dir / files["main"]
        main_target = self.storage.copy_into_job(main_source, context.job_id, main_source.name)
        frames: dict[str, str] = {}
        for key, filename in files.items():
            if key == "main":
                continue
            source = cache_dir / filename
            target = self.storage.copy_into_job(source, context.job_id, source.name)
            frames[key] = self.storage.public_url(context.base_url, target)
        return AssetRuntime(
            asset_id=planned_asset.asset_id,
            role=planned_asset.role,
            provider=ProviderKind.TRIPO,
            status=status,
            label=planned_asset.variant,
            url=self.storage.public_url(context.base_url, main_target),
            width=int(cached.metadata.get("width", 0)),
            height=int(cached.metadata.get("height", 0)),
            lane=planned_asset.metadata.get("lane"),
            collision_shape=cached.metadata.get("collision_shape"),
            frames=frames,
            metadata={"cache_key": cached.cache_key},
        )

    def _write_placeholder(self, planned_asset: PlannedAsset, spec: RunnerSpec, context: ProviderContext, reason: str) -> AssetRuntime:
        destination = self.storage.job_assets_dir(context.job_id) / f"{planned_asset.asset_id}.png"
        width, height = write_placeholder_sprite(destination, planned_asset.variant, spec.palette)
        frames = {"idle": self.storage.public_url(context.base_url, destination)} if planned_asset.role == AssetRole.CHARACTER else {}
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
            lane=planned_asset.metadata.get("lane"),
            collision_shape="rectangle",
            frames=frames,
        )
