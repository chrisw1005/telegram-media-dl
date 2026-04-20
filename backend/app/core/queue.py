"""In-process asyncio job queue with JSON snapshot for crash recovery.

Jobs are serialized to `data/queue.json` on every state change via atomic rename.
On startup, pending/running jobs are re-queued (running → pending).

A job represents one download operation: one media (chat_id, message_id) → one file.
Batch requests (multi-select) decompose into many jobs upstream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FLOOD_WAIT = "flood_wait"


@dataclass
class DownloadJob:
    id: str
    tg_user_id: int
    chat_id: int
    message_id: int
    kind: str  # "download" | "preview_upload" (Bot: to Saved Messages)
    dest_dir: str
    status: JobStatus = JobStatus.PENDING
    bytes_total: int = 0
    bytes_done: int = 0
    filename: str | None = None
    error: str | None = None
    flood_wait_until: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result_path: str | None = None
    send_to_saved: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DownloadJob:
        d = {**d, "status": JobStatus(d["status"])}
        return cls(**d)


JobHandler = Callable[["DownloadJob", Callable[[int, int], None]], Awaitable[None]]


class JobQueue:
    """Simple asyncio-based job queue with persistence."""

    def __init__(self, snapshot_path: Path, num_workers: int = 4) -> None:
        self._path = snapshot_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._jobs: dict[str, DownloadJob] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []
        self._handler: JobHandler | None = None
        self._snapshot_lock = asyncio.Lock()
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._all_subs: list[asyncio.Queue[dict[str, Any]]] = []

    # ---- lifecycle ----
    def set_handler(self, handler: JobHandler) -> None:
        self._handler = handler

    async def start(self) -> None:
        self._restore()
        for _ in range(self._num_workers):
            self._workers.append(asyncio.create_task(self._worker_loop()))

    async def stop(self) -> None:
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    # ---- persistence ----
    def _restore(self) -> None:
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("failed to read queue snapshot; starting empty", exc_info=True)
            return
        if not text.strip():
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("queue snapshot is not valid JSON (%s); starting empty", e)
            return
        for raw in data.get("jobs", []):
            job = DownloadJob.from_dict(raw)
            if job.status in (JobStatus.RUNNING, JobStatus.FLOOD_WAIT):
                job.status = JobStatus.PENDING
                job.started_at = None
            if job.status == JobStatus.PENDING:
                self._jobs[job.id] = job
                self._queue.put_nowait(job.id)
            elif job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                self._jobs[job.id] = job

    async def _snapshot(self) -> None:
        async with self._snapshot_lock:
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            payload = {"jobs": [j.to_dict() for j in self._jobs.values()]}
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            os.replace(tmp, self._path)

    # ---- operations ----
    async def enqueue(self, job: DownloadJob) -> str:
        if not job.id:
            job.id = uuid.uuid4().hex
        self._jobs[job.id] = job
        await self._queue.put(job.id)
        await self._snapshot()
        await self._publish(job, event="created")
        return job.id

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return False
        job.status = JobStatus.CANCELLED
        job.finished_at = time.time()
        await self._snapshot()
        await self._publish(job, event="cancelled")
        return True

    def get(self, job_id: str) -> DownloadJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self, tg_user_id: int | None = None) -> list[DownloadJob]:
        jobs = list(self._jobs.values())
        if tg_user_id is not None:
            jobs = [j for j in jobs if j.tg_user_id == tg_user_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    # ---- worker loop ----
    async def _worker_loop(self) -> None:
        while True:
            try:
                job_id = await self._queue.get()
                job = self._jobs.get(job_id)
                if job is None or job.status != JobStatus.PENDING:
                    continue
                if self._handler is None:
                    job.status = JobStatus.FAILED
                    job.error = "no handler registered"
                    await self._snapshot()
                    continue

                job.status = JobStatus.RUNNING
                job.started_at = time.time()
                await self._snapshot()
                await self._publish(job, event="started")

                def progress(done: int, total: int) -> None:
                    job.bytes_done = done
                    job.bytes_total = total or job.bytes_total
                    asyncio.create_task(self._publish(job, event="progress"))

                try:
                    await self._handler(job, progress)
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.COMPLETED
                    job.finished_at = time.time()
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # pragma: no cover — handler logs specifics
                    logger.exception("job %s failed", job_id)
                    job.status = JobStatus.FAILED
                    job.error = str(e)[:500]
                    job.finished_at = time.time()

                await self._snapshot()
                await self._publish(job, event="finished")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("worker loop error")

    # ---- pub/sub for WebSocket ----
    def subscribe(self, job_id: str | None = None) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        if job_id is None:
            self._all_subs.append(q)
        else:
            self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]], job_id: str | None = None) -> None:
        if job_id is None:
            if q in self._all_subs:
                self._all_subs.remove(q)
        else:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    async def _publish(self, job: DownloadJob, *, event: str) -> None:
        msg = {"event": event, "job": job.to_dict()}
        for q in list(self._all_subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
        for q in list(self._subscribers.get(job.id, [])):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
