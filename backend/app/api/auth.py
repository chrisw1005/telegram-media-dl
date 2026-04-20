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


class QRPasswordRequest(BaseModel):
    password: str


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


@router.post("/qr/{login_token}/password")
async def qr_password(
    login_token: str,
    req: QRPasswordRequest,
    state: StateDep,
    response: Response,
) -> dict:
    data = await state.login_manager.submit_qr_password(login_token, req.password)
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


class BotTokenRequest(BaseModel):
    bot_token: str


class MiniAppAuthRequest(BaseModel):
    init_data: str


@router.post("/miniapp")
async def miniapp_auth(
    req: MiniAppAuthRequest, state: StateDep, response: Response
) -> dict:
    """Verify Telegram Mini App initData HMAC and issue a session cookie.

    Requires BOT_TOKEN to be configured (initData is signed by the bot).
    The Telegram user MUST already have a completed MTProto session on file.
    """
    from app.miniapp.verify import InitDataError, verify_init_data

    if not state.secrets.bot_token:
        raise HTTPException(status_code=503, detail="bot_not_configured")

    try:
        verified = verify_init_data(req.init_data, state.secrets.bot_token)
    except InitDataError as e:
        raise HTTPException(status_code=401, detail=f"initdata_{e}") from e

    uid = verified.user.id
    if not state.acl.is_allowed(uid):
        raise HTTPException(status_code=403, detail="not_allowed")
    if not state.session_store.has_session(uid):
        return {"needs_login": True, "tg_user_id": uid}

    token = LoginManager.issue_api_token(uid)
    response.set_cookie(
        "tg_session",
        token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        path="/",
    )
    return {"ok": True, "tg_user_id": uid}


@router.post("/bot_token")
async def bot_token_exchange(
    req: BotTokenRequest, state: StateDep, response: Response
) -> dict:
    """Exchange a one-time deep-link token (issued by bot /start) for a web session
    cookie. Only works if the user already has a completed MTProto session.
    """
    from app.bot.handlers import resolve_deeplink_token

    uid = resolve_deeplink_token(req.bot_token)
    if uid is None:
        raise HTTPException(status_code=404, detail="token_invalid_or_expired")

    if not state.session_store.has_session(uid):
        return {"needs_login": True, "tg_user_id": uid}

    if not state.acl.is_allowed(uid):
        raise HTTPException(status_code=403, detail="not_allowed")

    token = LoginManager.issue_api_token(uid)
    response.set_cookie(
        "tg_session",
        token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
        path="/",
    )
    return {"ok": True, "tg_user_id": uid}


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
