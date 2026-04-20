"""Thumbnail / streaming / keyframe endpoints for quick preview."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.api.deps import StateDep, UserIdDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["preview"])


# ---- In-memory thumbnail LRU ----

_THUMB_MAX_BYTES = 50 * 1024 * 1024
_thumb_cache: OrderedDict[str, bytes] = OrderedDict()
_thumb_cache_bytes = 0
_thumb_lock = asyncio.Lock()


async def _thumb_cached(key: str) -> bytes | None:
    async with _thumb_lock:
        data = _thumb_cache.get(key)
        if data is not None:
            _thumb_cache.move_to_end(key)
        return data


async def _thumb_store(key: str, data: bytes) -> None:
    global _thumb_cache_bytes
    async with _thumb_lock:
        if key in _thumb_cache:
            _thumb_cache_bytes -= len(_thumb_cache[key])
            _thumb_cache.move_to_end(key)
        _thumb_cache[key] = data
        _thumb_cache_bytes += len(data)
        while _thumb_cache_bytes > _THUMB_MAX_BYTES and _thumb_cache:
            _, old = _thumb_cache.popitem(last=False)
            _thumb_cache_bytes -= len(old)


@router.get("/thumb/{chat_id}/{message_id}")
async def get_thumbnail(
    chat_id: int,
    message_id: int,
    uid: UserIdDep,
    state: StateDep,
) -> Response:
    key = f"{uid}:{chat_id}:{message_id}"
    cached = await _thumb_cached(key)
    if cached is not None:
        return Response(cached, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})

    client = await state.client_pool.get_client(uid)
    async with state.global_limiter:
        msg = await client.get_messages(chat_id, ids=message_id)
    if msg is None or msg.media is None:
        raise HTTPException(status_code=404, detail="not_found")

    async with state.global_limiter:
        data = await client.download_media(msg, thumb=-1, file=bytes)
    if not data:
        raise HTTPException(status_code=404, detail="no_thumbnail")
    await _thumb_store(key, data)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/stream/{chat_id}/{message_id}")
async def stream_media(
    chat_id: int,
    message_id: int,
    uid: UserIdDep,
    state: StateDep,
    request: Request,
) -> StreamingResponse:
    client = await state.client_pool.get_client(uid)
    async with state.global_limiter:
        msg = await client.get_messages(chat_id, ids=message_id)
    if msg is None or msg.media is None:
        raise HTTPException(status_code=404, detail="not_found")

    size = getattr(msg.file, "size", 0) or 0
    mime = getattr(msg.file, "mime_type", None) or "application/octet-stream"

    range_header = request.headers.get("range") or request.headers.get("Range")
    start = 0
    end = size - 1 if size > 0 else None

    if range_header and range_header.startswith("bytes="):
        r = range_header[6:]
        if "-" in r:
            s, e = r.split("-", 1)
            start = int(s) if s else 0
            if e:
                end = min(int(e), size - 1) if size else int(e)

    status_code = 200
    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime,
    }

    request_limit: int | None = None
    if range_header and size > 0 and end is not None:
        status_code = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        request_limit = end - start + 1
    elif size > 0:
        headers["Content-Length"] = str(size)

    async def body_iter():
        # preview_semaphore caps concurrent preview streams system-wide.
        # Each chunk fetch additionally draws from global_limiter so a long
        # stream doesn't monopolize Telegram API budget against other work.
        async with state.preview_semaphore:
            fetched = 0
            offset_aligned = (start // (64 * 1024)) * (64 * 1024)
            skip_head = start - offset_aligned
            async for chunk in client.iter_download(
                msg, offset=offset_aligned, request_size=64 * 1024
            ):
                if skip_head:
                    if skip_head >= len(chunk):
                        skip_head -= len(chunk)
                        continue
                    chunk = chunk[skip_head:]
                    skip_head = 0
                if request_limit is not None:
                    remaining = request_limit - fetched
                    if remaining <= 0:
                        break
                    if len(chunk) > remaining:
                        chunk = chunk[:remaining]
                async with state.global_limiter:
                    pass  # burn one permit per chunk we surface to the client
                yield chunk
                fetched += len(chunk)
                if request_limit is not None and fetched >= request_limit:
                    break

    return StreamingResponse(body_iter(), status_code=status_code, headers=headers)


@router.get("/keyframes/{chat_id}/{message_id}")
async def keyframes_list(
    chat_id: int,
    message_id: int,
    uid: UserIdDep,
    state: StateDep,
    trigger: bool = Query(False, description="If true, start extraction when not cached"),
):
    kf = state.keyframes
    meta = kf.load_meta(chat_id, message_id)
    if meta is not None:
        return {
            "ready": True,
            "frame_count": meta.frame_count,
            "offsets": meta.offsets,
            "duration_sec": meta.duration_sec,
            "urls": [
                f"/api/keyframes/{chat_id}/{message_id}/{i}.jpg"
                for i in range(meta.frame_count)
            ],
        }

    status = kf.status(chat_id, message_id)
    if trigger and status.state not in ("running", "completed"):
        client = await state.client_pool.get_client(uid)
        msg = await client.get_messages(chat_id, ids=message_id)
        size = getattr(msg.file, "size", 0) or 0 if msg else 0
        asyncio.create_task(kf.ensure_extracted(uid, chat_id, message_id, size_bytes=size))

    return {
        "ready": False,
        "status": status.state,
        "error": status.error,
        "progress_done": status.progress_frames_done,
        "progress_total": status.progress_frames_total,
    }


@router.get("/keyframes/{chat_id}/{message_id}/{idx}.jpg")
async def keyframe_file(
    chat_id: int,
    message_id: int,
    idx: int,
    uid: UserIdDep,
    state: StateDep,
) -> FileResponse:
    path: Path = state.keyframes.frame_path(chat_id, message_id, idx)
    if not path.exists():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
