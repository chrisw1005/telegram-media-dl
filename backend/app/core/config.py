"""Configuration loader. Reads config.yaml + env vars into a typed model."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class ConcurrencyConfig(BaseModel):
    per_user: int = 4
    global_rps: int = 20
    preview_semaphore: int = 6
    keyframe_workers: int = 2


class KeyframeConfig(BaseModel):
    density: Literal["low", "medium", "high"] = "medium"
    min_frames: int = 20
    max_frames: int = 120
    thumbnail_width: int = 320
    auto_extract_max_bytes: int = 50 * 1024 * 1024
    on_demand_max_bytes: int = 200 * 1024 * 1024


class AppConfig(BaseModel):
    deployment_mode: Literal["local", "public"] = "local"
    download_dir: Path = Field(default_factory=lambda: Path.home() / "Downloads" / "telegram")
    data_dir: Path = Path("data")
    admin_ids: list[int] = Field(default_factory=list)
    allowlist: list[int] = Field(default_factory=list)
    concurrency: ConcurrencyConfig = ConcurrencyConfig()
    keyframes: KeyframeConfig = KeyframeConfig()
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("download_dir", "data_dir", mode="before")
    @classmethod
    def _expand_path(cls, v: str | Path) -> Path:
        return Path(str(v)).expanduser()

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def users_dir(self) -> Path:
        return self.data_dir / "users"

    @property
    def queue_file(self) -> Path:
        return self.data_dir / "queue.json"

    @property
    def keyframes_cache_dir(self) -> Path:
        return self.data_dir / "cache" / "keyframes"

    @property
    def videos_temp_dir(self) -> Path:
        return self.data_dir / "cache" / "videos"

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.sessions_dir,
            self.users_dir,
            self.keyframes_cache_dir,
            self.videos_temp_dir,
            self.download_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


class Secrets(BaseModel):
    session_encryption_key: str
    tg_api_id: int
    tg_api_hash: str
    bot_token: str | None = None
    webhook_secret: str | None = None


@lru_cache(maxsize=1)
def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        return AppConfig()
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig(**raw)


@lru_cache(maxsize=1)
def load_secrets() -> Secrets:
    return Secrets(
        session_encryption_key=_require_env("SESSION_ENCRYPTION_KEY"),
        tg_api_id=int(_require_env("TG_API_ID")),
        tg_api_hash=_require_env("TG_API_HASH"),
        bot_token=os.getenv("BOT_TOKEN") or None,
        webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
    )


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value
