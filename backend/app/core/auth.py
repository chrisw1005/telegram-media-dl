"""Login orchestration.

Two flows:
  - QR login (`TelegramClient.qr_login`): poll until wait returns a user, or user scans.
  - Phone + OTP + optional 2FA: `send_code_request` → `sign_in(code)` → optional `sign_in(password=)`.

A session in-progress is identified by a short-lived `login_token`. The backend keeps the
fledgling `TelegramClient` in memory until login completes. On success, the Telethon session
file is encrypted under the Telegram user ID and the temp filename is renamed appropriately.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from app.core.acl import ACL
from app.core.client_pool import ClientPool
from app.core.config import AppConfig, Secrets
from app.core.session_store import SessionStore

logger = logging.getLogger(__name__)

LOGIN_TTL_SECONDS = 10 * 60
QR_POLL_INTERVAL = 2.0


@dataclass
class PendingLogin:
    token: str
    kind: str  # "qr" | "phone"
    client: TelegramClient
    temp_session_path: Path
    created_at: float = field(default_factory=time.time)
    phone_hash: str | None = None  # for phone flow
    phone_number: str | None = None
    qr_task: asyncio.Task | None = None
    qr_url: str | None = None
    qr_result: dict[str, Any] | None = None  # set when QR polls succeed or fail


class LoginManager:
    def __init__(
        self,
        config: AppConfig,
        secrets: Secrets,
        session_store: SessionStore,
        client_pool: ClientPool,
        acl: ACL,
    ) -> None:
        self._config = config
        self._secrets = secrets
        self._store = session_store
        self._pool = client_pool
        self._acl = acl
        self._pending: dict[str, PendingLogin] = {}
        self._lock = asyncio.Lock()

    def _new_temp_session(self) -> tuple[Path, str]:
        tid = uuid.uuid4().hex
        path = self._store.live_path(f"pending-{tid}")
        return path, tid

    def _make_client(self, session_path_stem: str) -> TelegramClient:
        return TelegramClient(
            session_path_stem,
            api_id=self._secrets.tg_api_id,
            api_hash=self._secrets.tg_api_hash,
            device_model="telegram-media-dl",
            app_version="0.1.0",
        )

    # ---- QR login ----
    async def start_qr(self) -> dict[str, Any]:
        token = secrets.token_urlsafe(24)
        path, tid = self._new_temp_session()
        stem = str(path).rsplit(".session", 1)[0]
        client = self._make_client(stem)
        await client.connect()
        qr = await client.qr_login()
        pending = PendingLogin(
            token=token,
            kind="qr",
            client=client,
            temp_session_path=path,
            qr_url=qr.url,
        )
        self._pending[token] = pending

        async def poll() -> None:
            try:
                while True:
                    try:
                        user = await qr.wait(QR_POLL_INTERVAL)
                        await self._finalize_login(pending, user)
                        pending.qr_result = {
                            "ok": True,
                            "tg_user_id": user.id,
                            "username": user.username,
                        }
                        return
                    except TimeoutError:
                        try:
                            await qr.recreate()
                            pending.qr_url = qr.url
                        except Exception:
                            logger.exception("qr recreate failed")
                            pending.qr_result = {"ok": False, "error": "qr_expired"}
                            return
                    except SessionPasswordNeededError:
                        pending.qr_result = {"ok": False, "error": "password_needed"}
                        return
                    except Exception as e:
                        logger.exception("qr poll failed")
                        pending.qr_result = {"ok": False, "error": str(e)[:200]}
                        return
            finally:
                pass

        pending.qr_task = asyncio.create_task(poll())
        return {"login_token": token, "qr_url": qr.url}

    async def refresh_qr(self, token: str) -> dict[str, Any]:
        pending = self._pending.get(token)
        if pending is None or pending.kind != "qr":
            return {"error": "invalid_token"}
        return {"qr_url": pending.qr_url, "result": pending.qr_result}

    # ---- Phone/OTP flow ----
    async def start_phone(self, phone_number: str) -> dict[str, Any]:
        token = secrets.token_urlsafe(24)
        path, _ = self._new_temp_session()
        stem = str(path).rsplit(".session", 1)[0]
        client = self._make_client(stem)
        await client.connect()
        sent = await client.send_code_request(phone_number)
        pending = PendingLogin(
            token=token,
            kind="phone",
            client=client,
            temp_session_path=path,
            phone_hash=sent.phone_code_hash,
            phone_number=phone_number,
        )
        self._pending[token] = pending
        return {"login_token": token}

    async def submit_qr_password(self, token: str, password: str) -> dict[str, Any]:
        """Continue a QR login after SessionPasswordNeededError."""
        pending = self._pending.get(token)
        if pending is None or pending.kind != "qr":
            return {"error": "invalid_token"}
        try:
            user = await pending.client.sign_in(password=password)
        except PasswordHashInvalidError:
            return {"error": "password_invalid"}
        except Exception as e:
            logger.exception("qr 2fa sign_in failed")
            return {"error": str(e)[:200]}
        try:
            await self._finalize_login(pending, user)
        except PermissionError:
            return {"error": "not_allowed"}
        return {"ok": True, "tg_user_id": user.id, "username": user.username}

    async def submit_code(
        self, token: str, code: str, password: str | None = None
    ) -> dict[str, Any]:
        pending = self._pending.get(token)
        if pending is None or pending.kind != "phone":
            return {"error": "invalid_token"}
        try:
            user = await pending.client.sign_in(
                phone=pending.phone_number, code=code, phone_code_hash=pending.phone_hash
            )
        except SessionPasswordNeededError:
            if not password:
                return {"error": "password_needed"}
            try:
                user = await pending.client.sign_in(password=password)
            except PasswordHashInvalidError:
                return {"error": "password_invalid"}
        except PhoneCodeInvalidError:
            return {"error": "code_invalid"}
        except PhoneCodeExpiredError:
            return {"error": "code_expired"}

        await self._finalize_login(pending, user)
        return {"ok": True, "tg_user_id": user.id, "username": user.username}

    # ---- shared finalize ----
    async def _finalize_login(self, pending: PendingLogin, user: Any) -> None:
        tg_user_id = int(user.id)
        if not self._acl.is_allowed(tg_user_id):
            await pending.client.disconnect()
            self._pending.pop(pending.token, None)
            for p in (pending.temp_session_path, Path(str(pending.temp_session_path) + "-journal")):
                if p.exists():
                    p.unlink()
            raise PermissionError(f"user {tg_user_id} not in allowlist")

        self._acl.bootstrap_admin(tg_user_id)

        await pending.client.disconnect()
        target_live = self._store.live_path(tg_user_id)
        target_live.parent.mkdir(parents=True, exist_ok=True)
        if target_live.exists():
            target_live.unlink()
        pending.temp_session_path.rename(target_live)
        self._store.persist(tg_user_id)
        self._pending.pop(pending.token, None)

    async def sweep_expired(self) -> None:
        now = time.time()
        expired = [
            t for t, p in self._pending.items() if now - p.created_at > LOGIN_TTL_SECONDS
        ]
        for t in expired:
            p = self._pending.pop(t, None)
            if p and p.client.is_connected():
                try:
                    await p.client.disconnect()
                except Exception:
                    pass
            if p and p.temp_session_path.exists():
                p.temp_session_path.unlink()

    # ---- session tokens for API auth (stateless, Fernet-signed) ----
    #
    # Cookie payload = Fernet(SESSION_ENCRYPTION_KEY).encrypt(json({uid, exp})).
    # Because the token is self-describing + cryptographically sealed, backend
    # reloads no longer invalidate existing cookies (the previous in-memory
    # dict lost all issued tokens whenever uvicorn reloaded on code change).
    API_TOKEN_TTL = 30 * 24 * 3600

    def _token_fernet(self) -> Fernet:
        # Reuse the same key that protects session files on disk.
        return Fernet(self._secrets.session_encryption_key.encode())

    def issue_api_token(self, tg_user_id: int) -> str:
        payload = json.dumps(
            {"uid": int(tg_user_id), "exp": int(time.time()) + self.API_TOKEN_TTL}
        ).encode()
        return self._token_fernet().encrypt(payload).decode()

    def resolve_api_token(self, token: str) -> int | None:
        try:
            payload = self._token_fernet().decrypt(token.encode())
            data = json.loads(payload)
        except (InvalidToken, ValueError):
            return None
        if int(data.get("exp", 0)) < time.time():
            return None
        uid = data.get("uid")
        return int(uid) if uid is not None else None

    def revoke_api_token(self, token: str) -> None:
        # Stateless tokens can't be centrally revoked without a blacklist.
        # On logout we just clear the cookie client-side; remaining TTL is
        # bounded by API_TOKEN_TTL.
        return None
