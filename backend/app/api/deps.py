"""FastAPI dependencies: shared app state and auth."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated

from aiolimiter import AsyncLimiter
from fastapi import Cookie, Depends, HTTPException, Request, status

from app.core.acl import ACL
from app.core.auth import LoginManager
from app.core.client_pool import ClientPool
from app.core.config import AppConfig, Secrets
from app.core.downloader import Downloader
from app.core.keyframe_extractor import KeyframeExtractor
from app.core.queue import JobQueue
from app.core.session_store import SessionStore


@dataclass
class AppState:
    config: AppConfig
    secrets: Secrets
    session_store: SessionStore
    client_pool: ClientPool
    acl: ACL
    login_manager: LoginManager
    queue: JobQueue
    downloader: Downloader
    keyframes: KeyframeExtractor
    # Shared rate-limit primitives used by every Telegram-bound endpoint.
    # Centralizing them means thumb/stream/keyframe/download all share one
    # system-wide budget, and adjusting concurrency config hits everything.
    global_limiter: AsyncLimiter
    preview_semaphore: asyncio.Semaphore


def get_state(request: Request) -> AppState:
    state = getattr(request.app.state, "app_state", None)
    if state is None:
        raise HTTPException(status_code=500, detail="app state not initialized")
    return state


StateDep = Annotated[AppState, Depends(get_state)]


def require_user(
    state: StateDep,
    session_token: Annotated[str | None, Cookie(alias="tg_session")] = None,
) -> int:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not_logged_in")
    uid = state.login_manager.resolve_api_token(session_token)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    if not state.acl.is_allowed(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_allowed")
    return uid


UserIdDep = Annotated[int, Depends(require_user)]


def require_admin(state: StateDep, uid: UserIdDep) -> int:
    if not state.acl.is_admin(uid):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_required")
    return uid


AdminIdDep = Annotated[int, Depends(require_admin)]
