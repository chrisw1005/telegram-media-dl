"""Per-user settings and admin endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import AdminIdDep, StateDep, UserIdDep

router = APIRouter(prefix="/api", tags=["settings"])


class UserSettings(BaseModel):
    download_dir: str | None = None
    preferred_concurrency: int | None = Field(default=None, ge=1, le=8)
    theme: str = "auto"  # "auto" | "light" | "dark"
    keyframe_density: str = "medium"  # "low" | "medium" | "high"


class AdminAcl(BaseModel):
    allowlist: list[int]
    admin_ids: list[int]


def _user_settings_path(state, uid: int) -> Path:
    return state.config.users_dir / f"{uid}.json"


def _load_user_settings(state, uid: int) -> UserSettings:
    p = _user_settings_path(state, uid)
    if p.exists():
        try:
            data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
            return UserSettings(**data)
        except (json.JSONDecodeError, TypeError):
            pass
    return UserSettings()


def _save_user_settings(state, uid: int, settings: UserSettings) -> None:
    p = _user_settings_path(state, uid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(p)


@router.get("/settings", response_model=UserSettings)
async def get_settings(uid: UserIdDep, state: StateDep) -> UserSettings:
    return _load_user_settings(state, uid)


@router.put("/settings", response_model=UserSettings)
async def put_settings(
    payload: UserSettings, uid: UserIdDep, state: StateDep
) -> UserSettings:
    _save_user_settings(state, uid, payload)
    return payload


@router.get("/admin/acl", response_model=AdminAcl)
async def admin_acl_get(admin_uid: AdminIdDep, state: StateDep) -> AdminAcl:
    return AdminAcl(
        allowlist=state.acl.list_allowed(),
        admin_ids=state.acl.list_admins(),
    )


class AclMutation(BaseModel):
    tg_user_id: int
    promote_to_admin: bool = False


@router.post("/admin/acl/add")
async def admin_acl_add(
    mut: AclMutation, admin_uid: AdminIdDep, state: StateDep
) -> AdminAcl:
    if mut.promote_to_admin:
        state.acl.add_admin(mut.tg_user_id)
    else:
        state.acl.add_allowed(mut.tg_user_id)
    return AdminAcl(
        allowlist=state.acl.list_allowed(),
        admin_ids=state.acl.list_admins(),
    )


@router.post("/admin/acl/remove")
async def admin_acl_remove(
    mut: AclMutation, admin_uid: AdminIdDep, state: StateDep
) -> AdminAcl:
    if mut.tg_user_id == admin_uid:
        raise HTTPException(status_code=400, detail="cannot_remove_self")
    state.acl.remove_allowed(mut.tg_user_id)
    return AdminAcl(
        allowlist=state.acl.list_allowed(),
        admin_ids=state.acl.list_admins(),
    )


@router.get("/info")
async def app_info(state: StateDep) -> dict:
    return {
        "deployment_mode": state.config.deployment_mode,
        "download_dir_default": str(state.config.download_dir),
    }
