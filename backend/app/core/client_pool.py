"""Per-user Telethon client cache.

- One `TelegramClient` instance per authenticated Telegram user ID.
- Clients are started lazily on first use, disconnected on idle timeout.
- A per-client `asyncio.Semaphore` caps parallel downloads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from telethon import TelegramClient

from app.core.config import AppConfig, Secrets
from app.core.session_store import SessionStore

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 15 * 60


@dataclass
class ClientEntry:
    client: TelegramClient
    sem: asyncio.Semaphore
    last_used: float


class ClientPool:
    def __init__(
        self,
        config: AppConfig,
        secrets: Secrets,
        session_store: SessionStore,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._store = session_store
        self._entries: dict[int, ClientEntry] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._reaper_task: asyncio.Task | None = None

    def _lock(self, tg_user_id: int) -> asyncio.Lock:
        lock = self._locks.get(tg_user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[tg_user_id] = lock
        return lock

    async def get_client(self, tg_user_id: int, *, connect: bool = True) -> TelegramClient:
        """Return a connected client for this user. Caller must ensure user is authorized."""
        async with self._lock(tg_user_id):
            entry = self._entries.get(tg_user_id)
            if entry is None:
                live_path = self._store.prepare_live(tg_user_id)
                client = TelegramClient(
                    str(live_path).rsplit(".session", 1)[0],
                    api_id=self._secrets.tg_api_id,
                    api_hash=self._secrets.tg_api_hash,
                    device_model="telegram-media-dl",
                    app_version="0.1.0",
                )
                entry = ClientEntry(
                    client=client,
                    sem=asyncio.Semaphore(self._config.concurrency.per_user),
                    last_used=time.monotonic(),
                )
                self._entries[tg_user_id] = entry

            if connect and not entry.client.is_connected():
                await entry.client.connect()
            entry.last_used = time.monotonic()
            return entry.client

    def semaphore(self, tg_user_id: int) -> asyncio.Semaphore:
        entry = self._entries.get(tg_user_id)
        if entry is None:
            raise RuntimeError(f"No client for user {tg_user_id}")
        return entry.sem

    def touch(self, tg_user_id: int) -> None:
        entry = self._entries.get(tg_user_id)
        if entry is not None:
            entry.last_used = time.monotonic()

    async def release(self, tg_user_id: int, *, persist: bool = True) -> None:
        """Disconnect and optionally re-encrypt the session."""
        async with self._lock(tg_user_id):
            entry = self._entries.pop(tg_user_id, None)
            if entry is None:
                return
            try:
                if entry.client.is_connected():
                    await entry.client.disconnect()
            finally:
                if persist:
                    self._store.persist(tg_user_id)
                self._store.drop_live(tg_user_id)

    async def shutdown(self) -> None:
        if self._reaper_task is not None:
            self._reaper_task.cancel()
        for uid in list(self._entries):
            await self.release(uid, persist=True)

    async def _reap_idle(self) -> None:
        while True:
            try:
                await asyncio.sleep(60)
                now = time.monotonic()
                stale = [
                    uid
                    for uid, e in self._entries.items()
                    if now - e.last_used > IDLE_TIMEOUT_SECONDS
                ]
                for uid in stale:
                    logger.info("reaping idle client for user %s", uid)
                    await self.release(uid, persist=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("idle reaper error")

    def start_reaper(self) -> None:
        if self._reaper_task is None:
            self._reaper_task = asyncio.create_task(self._reap_idle())
