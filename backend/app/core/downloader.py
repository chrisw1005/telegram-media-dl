"""Concurrent media downloader with rate limiting and FLOOD_WAIT handling."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

from aiolimiter import AsyncLimiter
from telethon.errors import FloodWaitError
from telethon.tl.custom.message import Message
from telethon.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
)

from app.core.client_pool import ClientPool
from app.core.config import AppConfig
from app.core.queue import DownloadJob, JobStatus

logger = logging.getLogger(__name__)


def _safe_filename(raw: str | None, fallback: str) -> str:
    if not raw:
        return fallback
    bad = '/\\:*?"<>|\0'
    cleaned = "".join("_" if c in bad else c for c in raw).strip()
    return cleaned[:200] or fallback


class Downloader:
    def __init__(
        self, config: AppConfig, pool: ClientPool, global_limiter: AsyncLimiter
    ) -> None:
        self._config = config
        self._pool = pool
        self._global_limiter = global_limiter

    async def fetch_message(self, tg_user_id: int, chat_id: int, message_id: int) -> Message:
        client = await self._pool.get_client(tg_user_id)
        msg = await client.get_messages(chat_id, ids=message_id)
        if msg is None:
            raise FileNotFoundError(f"message not found: {chat_id}/{message_id}")
        return msg

    async def run_job(
        self, job: DownloadJob, on_progress: Callable[[int, int], None]
    ) -> None:
        client = await self._pool.get_client(job.tg_user_id)
        sem = self._pool.semaphore(job.tg_user_id)

        async with sem:
            try:
                msg = await client.get_messages(job.chat_id, ids=job.message_id)
                if msg is None or msg.media is None:
                    raise FileNotFoundError(f"no media at {job.chat_id}/{job.message_id}")

                filename = _safe_filename(getattr(msg.file, "name", None), f"msg-{job.message_id}")
                ext = Path(filename).suffix
                if not ext and getattr(msg.file, "ext", None):
                    filename += msg.file.ext

                dest_dir = Path(job.dest_dir).expanduser()
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / filename
                if dest_path.exists():
                    dest_path = _with_sequence_suffix(dest_path)

                job.filename = filename
                job.bytes_total = getattr(msg.file, "size", 0) or 0

                done = 0

                def progress_cb(current: int, total: int) -> None:
                    nonlocal done
                    done = current
                    on_progress(current, total)

                attempt = 0
                while True:
                    try:
                        async with self._global_limiter:
                            saved_to = await client.download_media(
                                msg,
                                file=str(dest_path),
                                progress_callback=progress_cb,
                            )
                        if saved_to is None:
                            raise RuntimeError("download returned None")
                        job.result_path = str(saved_to)
                        break
                    except FloodWaitError as flood:
                        attempt += 1
                        wait = int(getattr(flood, "seconds", 30)) + 1
                        logger.warning(
                            "FLOOD_WAIT %ss for job %s (attempt %d)", wait, job.id, attempt
                        )
                        job.status = JobStatus.FLOOD_WAIT
                        job.flood_wait_until = time.time() + wait
                        await asyncio.sleep(wait)
                        job.status = JobStatus.RUNNING
                        if attempt > 4:
                            raise

                # Post-download: optional re-upload to Saved Messages (Bot flow)
                if job.send_to_saved and job.result_path:
                    try:
                        await self._send_to_saved(client, job)
                    except Exception:
                        logger.exception("send_to_saved failed for job %s", job.id)
                        # Not fatal — keep the downloaded file; record the error.
                        job.error = (job.error or "") + "; saved_messages_upload_failed"
            except asyncio.CancelledError:
                raise

    async def _send_to_saved(self, client, job: DownloadJob) -> None:
        """Upload the downloaded file to the user's Saved Messages (chat 'me').

        Re-uses the source message's attributes (video duration/dims/streaming,
        audio duration/title, filename, animated flag) and its server-provided
        thumbnail so the re-upload shows the same preview + length Telegram
        had on the original. Uses the user's own MTProto session, so the
        2GB / 4GB Premium limits apply instead of the Bot API 50MB restriction.
        """
        size = job.bytes_total or 0
        if size > self._config.bot_large_file_fallback_bytes:
            logger.info(
                "file too large (%d bytes) for saved-messages upload; keeping server copy only",
                size,
            )
            return

        attributes: list = []
        thumb: bytes | None = None
        supports_streaming = False
        mime_type: str | None = None

        try:
            orig = await client.get_messages(job.chat_id, ids=job.message_id)
        except Exception:
            orig = None

        if orig is not None and getattr(orig, "document", None) is not None:
            for attr in orig.document.attributes:
                if isinstance(
                    attr,
                    (
                        DocumentAttributeVideo,
                        DocumentAttributeAudio,
                        DocumentAttributeFilename,
                        DocumentAttributeAnimated,
                    ),
                ):
                    attributes.append(attr)
                    if isinstance(attr, DocumentAttributeVideo):
                        supports_streaming = True
            mime_type = getattr(orig.document, "mime_type", None)
            try:
                thumb_bytes = await client.download_media(orig, thumb=-1, file=bytes)
                if thumb_bytes:
                    thumb = thumb_bytes
            except Exception:
                logger.debug("thumb download failed for %s", job.id)

        async with self._global_limiter:
            await client.send_file(
                "me",
                job.result_path,
                caption=job.filename or Path(job.result_path).name,
                attributes=attributes or None,
                thumb=thumb,
                supports_streaming=supports_streaming,
                mime_type=mime_type,
                force_document=False,
            )


def _with_sequence_suffix(path: Path) -> Path:
    parent = path.parent
    stem = path.stem
    suffix = path.suffix
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1
