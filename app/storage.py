from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import quote

from app.models import GameJob, ProviderKind, StoredCacheEntry


class GameStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)

    @property
    def jobs_root(self) -> Path:
        return self.root / "games"

    @property
    def cache_root(self) -> Path:
        return self.root / "cache"

    def job_dir(self, job_id: str) -> Path:
        path = self.jobs_root / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_assets_dir(self, job_id: str) -> Path:
        path = self.job_dir(job_id) / "assets"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_dir(self, provider: ProviderKind, cache_key: str) -> Path:
        path = self.cache_root / provider.value / cache_key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, path: Path, payload: object) -> None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def save_job(self, job: GameJob) -> None:
        self.write_json(self.job_dir(job.job_id) / "job.json", job.model_dump(mode="json"))

    def load_all_jobs(self) -> dict[str, GameJob]:
        jobs: dict[str, GameJob] = {}
        if not self.jobs_root.exists():
            return jobs
        for path in self.jobs_root.glob("*/job.json"):
            loaded = GameJob.model_validate_json(path.read_text(encoding="utf-8"))
            jobs[loaded.job_id] = loaded
        return jobs

    def uploads_dir(self) -> Path:
        path = self.root / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_named_payload(self, job_id: str, filename: str, payload: object) -> None:
        self.write_json(self.job_dir(job_id) / filename, payload)

    def public_url(self, base_url: str, path: Path) -> str:
        relative = path.relative_to(self.root).as_posix()
        return f"{base_url.rstrip('/')}/files/{quote(relative)}"

    def cache_entry_path(self, provider: ProviderKind, cache_key: str) -> Path:
        return self.cache_dir(provider, cache_key) / "entry.json"

    def save_cache_entry(self, entry: StoredCacheEntry) -> None:
        self.write_json(self.cache_entry_path(entry.provider, entry.cache_key), entry.model_dump(mode="json"))

    def load_cache_entry(self, provider: ProviderKind, cache_key: str) -> StoredCacheEntry | None:
        path = self.cache_entry_path(provider, cache_key)
        if not path.exists():
            return None
        return StoredCacheEntry.model_validate_json(path.read_text(encoding="utf-8"))

    def copy_into_job(self, source: Path, job_id: str, filename: str) -> Path:
        destination = self.job_assets_dir(job_id) / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def cached_theme_dir(self, provider: ProviderKind, theme_key: str) -> Path:
        path = self.cache_root / f"{provider.value}-theme" / theme_key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def copy_tree(self, source: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for item in source.iterdir():
            target = destination / item.name
            if item.is_dir():
                self.copy_tree(item, target)
            else:
                shutil.copyfile(item, target)
