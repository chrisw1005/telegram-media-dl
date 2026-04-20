"""Chat and message listing endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from telethon.tl.types import (
    Channel,
    Chat,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    User,
)

from app.api.deps import StateDep, UserIdDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chats"])


class ChatItem(BaseModel):
    id: int
    title: str
    username: str | None = None
    kind: str  # "user" | "group" | "channel"
    unread_count: int = 0
    last_message: str | None = None


class MediaItem(BaseModel):
    chat_id: int
    message_id: int
    kind: str  # "photo" | "video" | "document" | "audio" | "voice"
    filename: str | None = None
    size: int = 0
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    mime_type: str | None = None
    date_ts: float = 0.0
    has_animated_preview: bool = False


class MessageMeta(BaseModel):
    chat_id: int
    message_id: int
    filename: str | None = None
    size: int = 0
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    mime_type: str | None = None
    date_ts: float = 0.0
    sender_id: int | None = None
    sender_name: str | None = None


def _classify(entity) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "channel" if entity.broadcast else "group"
    if isinstance(entity, Chat):
        return "group"
    return "user"


def _chat_title(entity) -> str:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p).strip() or entity.username or str(entity.id)
    return getattr(entity, "title", None) or str(entity.id)


def _username(entity) -> str | None:
    return getattr(entity, "username", None)


def _media_kind(msg) -> str | None:
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.voice:
        return "voice"
    if msg.audio:
        return "audio"
    if msg.document:
        return "document"
    return None


def _extract_media_meta(msg) -> dict:
    kind = _media_kind(msg)
    if kind is None:
        return {}
    size = getattr(msg.file, "size", 0) or 0
    filename = getattr(msg.file, "name", None)
    mime = getattr(msg.file, "mime_type", None)
    width = height = 0
    duration = 0.0
    if msg.document:
        for attr in msg.document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                width, height = attr.w, attr.h
                duration = float(attr.duration)
            elif isinstance(attr, DocumentAttributeAudio):
                duration = float(attr.duration)
            elif isinstance(attr, DocumentAttributeFilename):
                filename = filename or attr.file_name
    elif msg.photo:
        for size_obj in getattr(msg.photo, "sizes", []) or []:
            w = getattr(size_obj, "w", 0) or 0
            h = getattr(size_obj, "h", 0) or 0
            if w > width:
                width, height = w, h
    return {
        "kind": kind,
        "filename": filename,
        "size": size,
        "duration_sec": duration,
        "width": width,
        "height": height,
        "mime_type": mime,
    }


@router.get("/chats", response_model=list[ChatItem])
async def list_chats(
    uid: UserIdDep,
    state: StateDep,
    limit: int = Query(100, ge=1, le=500),
) -> list[ChatItem]:
    client = await state.client_pool.get_client(uid)
    dialogs = await client.get_dialogs(limit=limit)
    items: list[ChatItem] = []
    for d in dialogs:
        entity = d.entity
        last_msg = d.message.message if d.message and getattr(d.message, "message", None) else None
        items.append(
            ChatItem(
                id=int(d.id),
                title=_chat_title(entity),
                username=_username(entity),
                kind=_classify(entity),
                unread_count=int(d.unread_count or 0),
                last_message=last_msg,
            )
        )
    return items


@router.get("/chats/{chat_id}/media", response_model=dict)
async def list_chat_media(
    chat_id: int,
    uid: UserIdDep,
    state: StateDep,
    offset_id: int = 0,
    limit: int = Query(60, ge=1, le=200),
    kind: str | None = Query(None, pattern="^(photo|video|document|audio|voice)$"),
) -> dict:
    client = await state.client_pool.get_client(uid)

    filter_obj = None
    if kind == "photo":
        from telethon.tl.types import InputMessagesFilterPhotos
        filter_obj = InputMessagesFilterPhotos()
    elif kind == "video":
        from telethon.tl.types import InputMessagesFilterVideo
        filter_obj = InputMessagesFilterVideo()
    elif kind == "document":
        from telethon.tl.types import InputMessagesFilterDocument
        filter_obj = InputMessagesFilterDocument()
    elif kind == "audio":
        from telethon.tl.types import InputMessagesFilterMusic
        filter_obj = InputMessagesFilterMusic()
    elif kind == "voice":
        from telethon.tl.types import InputMessagesFilterVoice
        filter_obj = InputMessagesFilterVoice()
    else:
        from telethon.tl.types import InputMessagesFilterPhotoVideoDocuments
        filter_obj = InputMessagesFilterPhotoVideoDocuments()

    msgs = await client.get_messages(
        chat_id,
        limit=limit,
        offset_id=offset_id,
        filter=filter_obj,
    )

    items: list[MediaItem] = []
    for msg in msgs:
        meta = _extract_media_meta(msg)
        if not meta:
            continue
        items.append(
            MediaItem(
                chat_id=chat_id,
                message_id=msg.id,
                date_ts=msg.date.timestamp() if msg.date else 0.0,
                **meta,
            )
        )

    next_offset = msgs[-1].id if msgs else 0
    return {"items": items, "next_offset": next_offset, "has_more": len(msgs) == limit}


@router.get("/messages/{chat_id}/{message_id}/meta", response_model=MessageMeta)
async def message_meta(
    chat_id: int,
    message_id: int,
    uid: UserIdDep,
    state: StateDep,
) -> MessageMeta:
    client = await state.client_pool.get_client(uid)
    msg = await client.get_messages(chat_id, ids=message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="not_found")
    meta = _extract_media_meta(msg)
    sender_name: str | None = None
    sender_id: int | None = None
    if msg.sender:
        sender_id = int(getattr(msg.sender, "id", 0)) or None
        sender_name = _chat_title(msg.sender)
    return MessageMeta(
        chat_id=chat_id,
        message_id=message_id,
        date_ts=msg.date.timestamp() if msg.date else 0.0,
        sender_id=sender_id,
        sender_name=sender_name,
        **{k: v for k, v in meta.items() if k != "kind"},
    )
