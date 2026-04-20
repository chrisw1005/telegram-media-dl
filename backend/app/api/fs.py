"""Filesystem picker (local deployment only).

Lets the Web UI browse directories on the server so the user can pick a download target.
Disabled when `deployment_mode == 'public'` — returns 403.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import StateDep, UserIdDep

router = APIRouter(prefix="/api/fs", tags=["fs"])


class DirEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class ListResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[DirEntry]


@router.get("/list", response_model=ListResponse)
async def list_dir(
    uid: UserIdDep,
    state: StateDep,
    path: str = Query(default="~"),
    show_hidden: bool = Query(default=False),
) -> ListResponse:
    if state.config.deployment_mode != "local":
        raise HTTPException(status_code=403, detail="disabled_in_public_mode")

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise HTTPException(status_code=404, detail="not_a_directory")

    entries: list[DirEntry] = []
    try:
        with os.scandir(resolved) as it:
            for entry in it:
                if not show_hidden and entry.name.startswith("."):
                    continue
                if not entry.is_dir(follow_symlinks=False):
                    continue
                entries.append(
                    DirEntry(name=entry.name, path=str(resolved / entry.name), is_dir=True)
                )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail="permission_denied") from e

    entries.sort(key=lambda e: e.name.lower())

    parent = str(resolved.parent) if resolved.parent != resolved else None
    return ListResponse(path=str(resolved), parent=parent, entries=entries)


@router.post("/mkdir")
async def make_dir(
    uid: UserIdDep,
    state: StateDep,
    path: str = Query(...),
) -> dict:
    if state.config.deployment_mode != "local":
        raise HTTPException(status_code=403, detail="disabled_in_public_mode")
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": str(p.resolve())}
