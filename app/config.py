from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    public_base_url: str = Field(default="http://127.0.0.1:8000", alias="PUBLIC_BASE_URL")
    data_root: Path = Field(default=Path("data"), alias="DATA_ROOT")
    tripo_asset_base_url: str = Field(default="", alias="TRIPO_ASSET_BASE_URL")
    tripo_poll_interval_seconds: float = Field(default=3.0, alias="TRIPO_POLL_INTERVAL_SECONDS")
    tripo_timeout_seconds: float = Field(default=300.0, alias="TRIPO_TIMEOUT_SECONDS")
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    byteplus_base_url: str = Field(
        default="https://ark.ap-southeast.bytepluses.com/api/v3",
        alias="BYTEPLUS_BASE_URL",
    )
    byteplus_model: str = Field(default="seedream-3-0-t2i-250415", alias="BYTEPLUS_MODEL")
    byteplus_image_size: str = Field(default="1024x1024", alias="BYTEPLUS_IMAGE_SIZE")
    byteplus_timeout_seconds: float = Field(default=60.0, alias="BYTEPLUS_TIMEOUT_SECONDS")
    phaser_cdn_url: str = Field(
        default="https://cdn.jsdelivr.net/npm/phaser@3/dist/phaser.min.js",
        alias="PHASER_CDN_URL",
    )
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        alias="GEMINI_BASE_URL",
    )
    enable_gemini_validation: bool = Field(default=True, alias="ENABLE_GEMINI_VALIDATION")
    default_viewport_width: int = Field(default=1280, alias="DEFAULT_VIEWPORT_WIDTH")
    default_viewport_height: int = Field(default=720, alias="DEFAULT_VIEWPORT_HEIGHT")

    @property
    def jobs_root(self) -> Path:
        return self.data_root / "games"

    @property
    def cache_root(self) -> Path:
        return self.data_root / "cache"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
