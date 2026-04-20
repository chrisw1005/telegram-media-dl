"""Keyframe extraction using imageio-ffmpeg's bundled ffmpeg binary.

For each video:
 1. Telethon downloads the video into `data/cache/videos/{msg_id}.mp4` (tmp).
 2. ffmpeg extracts N evenly-distributed frames (`N` adaptive to duration).
 3. Frames saved to `data/cache/keyframes/{chat_id}/{msg_id}/frame_XXXX.jpg` + `meta.json`.
 4. tmp video is deleted.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import imageio_ffmpeg
from aiolimiter import AsyncLimiter

from app.core.client_pool import ClientPool
from app.core.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class KeyframeMeta:
    msg_id: int
    chat_id: int
    duration_sec: float
    frame_count: int
    offsets: list[float]  # seconds
    thumbnail_width: int
    ffmpeg_version: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class ExtractionStatus:
    state: str  # "pending" | "running" | "completed" | "failed" | "skipped"
    progress_frames_done: int = 0
    progress_frames_total: int = 0
    error: str | None = None


class KeyframeExtractor:
    def __init__(
        self,
        config: AppConfig,
        pool: ClientPool,
        global_limiter: AsyncLimiter,
    ) -> None:
        self._config = config
        self._pool = pool
        self._global_limiter = global_limiter
        self._ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self._statuses: dict[str, ExtractionStatus] = {}  # key=f"{chat_id}:{msg_id}"
        self._locks: dict[str, asyncio.Lock] = {}
        # keyframe_workers gates CPU-bound ffmpeg jobs (not network).
        self._worker_sem = asyncio.Semaphore(config.concurrency.keyframe_workers)
        self._subscribers: list[asyncio.Queue[dict]] = []

    def status_key(self, chat_id: int, msg_id: int) -> str:
        return f"{chat_id}:{msg_id}"

    def _lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def out_dir(self, chat_id: int, msg_id: int) -> Path:
        return self._config.keyframes_cache_dir / str(chat_id) / str(msg_id)

    def meta_path(self, chat_id: int, msg_id: int) -> Path:
        return self.out_dir(chat_id, msg_id) / "meta.json"

    def load_meta(self, chat_id: int, msg_id: int) -> KeyframeMeta | None:
        p = self.meta_path(chat_id, msg_id)
        if not p.exists():
            return None
        try:
            return KeyframeMeta(**json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return None

    def status(self, chat_id: int, msg_id: int) -> ExtractionStatus:
        key = self.status_key(chat_id, msg_id)
        return self._statuses.get(key, ExtractionStatus(state="pending"))

    def adaptive_frame_count(self, duration_sec: float) -> int:
        cfg = self._config.keyframes
        divisor = {"low": 10, "medium": 5, "high": 2}[cfg.density]
        target = round(duration_sec / divisor) if duration_sec > 0 else cfg.min_frames
        return max(cfg.min_frames, min(cfg.max_frames, target))

    async def ensure_extracted(
        self,
        tg_user_id: int,
        chat_id: int,
        msg_id: int,
        *,
        size_bytes: int | None = None,
    ) -> KeyframeMeta | None:
        """Extract if not present. Returns meta (possibly None if skipped/failed)."""
        cached = self.load_meta(chat_id, msg_id)
        if cached is not None:
            return cached

        key = self.status_key(chat_id, msg_id)
        async with self._lock(key):
            cached = self.load_meta(chat_id, msg_id)
            if cached is not None:
                return cached

            if size_bytes is not None and size_bytes > self._config.keyframes.on_demand_max_bytes:
                self._statuses[key] = ExtractionStatus(state="skipped", error="too_large")
                return None

            self._statuses[key] = ExtractionStatus(state="running")
            await self._publish(chat_id, msg_id)
            try:
                meta = await self._extract(tg_user_id, chat_id, msg_id)
                self._statuses[key] = ExtractionStatus(
                    state="completed",
                    progress_frames_done=meta.frame_count,
                    progress_frames_total=meta.frame_count,
                )
                await self._publish(chat_id, msg_id)
                return meta
            except Exception as e:
                logger.exception("keyframe extract failed for %s:%s", chat_id, msg_id)
                self._statuses[key] = ExtractionStatus(state="failed", error=str(e)[:300])
                await self._publish(chat_id, msg_id)
                return None

    async def _extract(self, tg_user_id: int, chat_id: int, msg_id: int) -> KeyframeMeta:
        async with self._worker_sem:
            client = await self._pool.get_client(tg_user_id)
            async with self._global_limiter:
                msg = await client.get_messages(chat_id, ids=msg_id)
            if msg is None or msg.media is None:
                raise FileNotFoundError(f"no media at {chat_id}/{msg_id}")

            duration = float(getattr(msg.file, "duration", 0) or 0)
            if duration <= 0:
                raise ValueError("unknown duration; not a video?")

            frame_count = self.adaptive_frame_count(duration)
            out_dir = self.out_dir(chat_id, msg_id)
            out_dir.mkdir(parents=True, exist_ok=True)

            temp_dir = self._config.videos_temp_dir
            temp_dir.mkdir(parents=True, exist_ok=True)
            tmp_video = temp_dir / f"{msg_id}-{int(time.time())}.mp4"

            try:
                async with self._global_limiter:
                    await client.download_media(msg, file=str(tmp_video))
                offsets = [
                    (i + 0.5) * (duration / frame_count) for i in range(frame_count)
                ]
                await self._run_ffmpeg(tmp_video, out_dir, offsets)
            finally:
                if tmp_video.exists():
                    tmp_video.unlink()

            meta = KeyframeMeta(
                msg_id=msg_id,
                chat_id=chat_id,
                duration_sec=duration,
                frame_count=frame_count,
                offsets=offsets,
                thumbnail_width=self._config.keyframes.thumbnail_width,
                ffmpeg_version="imageio-ffmpeg",
            )
            self.meta_path(chat_id, msg_id).write_text(
                json.dumps(asdict(meta), indent=2), encoding="utf-8"
            )
            return meta

    async def _run_ffmpeg(self, video: Path, out_dir: Path, offsets: list[float]) -> None:
        """Extract frames at specific offsets using ffmpeg."""
        width = self._config.keyframes.thumbnail_width

        def run_one(idx: int, offset: float) -> None:
            target = out_dir / f"frame_{idx:04d}.jpg"
            if target.exists():
                return
            cmd = [
                self._ffmpeg,
                "-loglevel", "error",
                "-ss", f"{offset:.3f}",
                "-i", str(video),
                "-frames:v", "1",
                "-vf", f"scale={width}:-2",
                "-q:v", "5",
                "-y",
                str(target),
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg failed (offset={offset}): {proc.stderr.decode('utf-8', errors='replace')[:200]}"
                )

        # Run sequentially inside the global_sem-bound task to avoid CPU thrash
        for idx, offset in enumerate(offsets):
            await asyncio.to_thread(run_one, idx, offset)

    # ---- pub/sub for progress WebSocket (optional) ----
    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    async def _publish(self, chat_id: int, msg_id: int) -> None:
        msg = {
            "chat_id": chat_id,
            "msg_id": msg_id,
            "status": asdict(self.status(chat_id, msg_id)),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def frame_path(self, chat_id: int, msg_id: int, idx: int) -> Path:
        return self.out_dir(chat_id, msg_id) / f"frame_{idx:04d}.jpg"
