"""Download endpoints: enqueue, list, cancel, live progress via WebSocket."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import StateDep, UserIdDep
from app.core.queue import DownloadJob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["download"])


class DownloadRequest(BaseModel):
    chat_id: int
    message_ids: list[int]
    dest_dir: str | None = None
    send_to_saved: bool = False


class DownloadResponse(BaseModel):
    job_ids: list[str]


@router.post("/download", response_model=DownloadResponse)
async def enqueue_download(
    req: DownloadRequest,
    uid: UserIdDep,
    state: StateDep,
) -> DownloadResponse:
    dest_dir = req.dest_dir or str(state.config.download_dir)
    if state.config.deployment_mode == "public":
        dest_dir = str(state.config.download_dir / str(uid))

    p = Path(dest_dir).expanduser()
    if state.config.deployment_mode == "local" and not p.is_absolute():
        raise HTTPException(status_code=400, detail="dest_dir must be absolute in local mode")

    ids: list[str] = []
    for mid in req.message_ids:
        job = DownloadJob(
            id="",
            tg_user_id=uid,
            chat_id=req.chat_id,
            message_id=mid,
            kind="download",
            dest_dir=str(p),
            send_to_saved=req.send_to_saved,
        )
        jid = await state.queue.enqueue(job)
        ids.append(jid)
    return DownloadResponse(job_ids=ids)


@router.get("/jobs")
async def list_jobs(uid: UserIdDep, state: StateDep) -> dict:
    jobs = state.queue.list_jobs(tg_user_id=uid)
    return {"jobs": [j.to_dict() for j in jobs]}


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, uid: UserIdDep, state: StateDep) -> dict:
    job = state.queue.get(job_id)
    if job is None or job.tg_user_id != uid:
        raise HTTPException(status_code=404, detail="not_found")
    ok = await state.queue.cancel(job_id)
    return {"ok": ok, "status": job.status.value if job else None}


@router.websocket("/ws/downloads")
async def ws_downloads(
    websocket: WebSocket,
    state: StateDep,
    tg_session: str | None = Cookie(default=None),
) -> None:
    await websocket.accept()
    uid = state.login_manager.resolve_api_token(tg_session) if tg_session else None
    if uid is None or not state.acl.is_allowed(uid):
        await websocket.send_json({"error": "unauthorized"})
        await websocket.close()
        return

    sub = state.queue.subscribe()

    # Send initial snapshot
    await websocket.send_json(
        {
            "event": "snapshot",
            "jobs": [j.to_dict() for j in state.queue.list_jobs(tg_user_id=uid)],
        }
    )

    try:
        while True:
            pull = asyncio.create_task(sub.get())
            recv = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                [pull, recv], return_when=asyncio.FIRST_COMPLETED
            )
            for p in pending:
                p.cancel()
            if pull in done:
                msg = pull.result()
                job = msg.get("job", {})
                if job.get("tg_user_id") != uid:
                    continue
                await websocket.send_json(msg)
            if recv in done:
                # Ignore client messages for now (could add per-job subscribe later)
                pass
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("ws_downloads error")
    finally:
        state.queue.unsubscribe(sub)
