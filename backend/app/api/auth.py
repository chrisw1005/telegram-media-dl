"""Authentication endpoints: QR login, phone/OTP fallback, session management."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel

from app.api.deps import StateDep, UserIdDep
from app.core.auth import LoginManager

router = APIRouter(prefix="/api/auth", tags=["auth"])


class QRStartResponse(BaseModel):
    login_token: str
    qr_url: str


class QRPollResponse(BaseModel):
    qr_url: str | None = None
    result: dict | None = None


class PhoneStartRequest(BaseModel):
    phone_number: str


class PhoneCodeRequest(BaseModel):
    login_token: str
    code: str
    password: str | None = None


class MeResponse(BaseModel):
    tg_user_id: int
    is_admin: bool


@router.post("/qr/start", response_model=QRStartResponse)
async def qr_start(state: StateDep) -> QRStartResponse:
    data = await state.login_manager.start_qr()
    return QRStartResponse(**data)


@router.get("/qr/{login_token}", response_model=QRPollResponse)
async def qr_poll(login_token: str, state: StateDep, response: Response) -> QRPollResponse:
    data = await state.login_manager.refresh_qr(login_token)
    if data.get("error") == "invalid_token":
        raise HTTPException(status_code=404, detail="invalid_token")
    result = data.get("result")
    if result and result.get("ok"):
        token = LoginManager.issue_api_token(int(result["tg_user_id"]))
        response.set_cookie(
            "tg_session",
            token,
            httponly=True,
            samesite="lax",
            max_age=30 * 24 * 3600,
            path="/",
        )
    return QRPollResponse(qr_url=data.get("qr_url"), result=result)


@router.post("/phone/start")
async def phone_start(req: PhoneStartRequest, state: StateDep) -> dict:
    data = await state.login_manager.start_phone(req.phone_number)
    return data


@router.post("/phone/code")
async def phone_code(req: PhoneCodeRequest, state: StateDep, response: Response) -> dict:
    data = await state.login_manager.submit_code(
        req.login_token, req.code, req.password
    )
    if data.get("ok"):
        token = LoginManager.issue_api_token(int(data["tg_user_id"]))
        response.set_cookie(
            "tg_session",
            token,
            httponly=True,
            samesite="lax",
            max_age=30 * 24 * 3600,
            path="/",
        )
    return data


@router.get("/me", response_model=MeResponse)
async def me(uid: UserIdDep, state: StateDep) -> MeResponse:
    return MeResponse(tg_user_id=uid, is_admin=state.acl.is_admin(uid))


@router.post("/logout")
async def logout(
    response: Response,
    state: StateDep,
    session_token: str | None = Cookie(default=None, alias="tg_session"),
) -> dict:
    if session_token:
        uid = LoginManager.resolve_api_token(session_token)
        LoginManager.revoke_api_token(session_token)
        if uid is not None:
            await state.client_pool.release(uid, persist=True)
    response.delete_cookie("tg_session", path="/")
    return {"ok": True}
