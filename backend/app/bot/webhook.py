"""Bot webhook: mounts python-telegram-bot Application into FastAPI.

Startup:
  - Build PTB Application with the configured BOT_TOKEN
  - Register handlers from app.bot.handlers
  - Call Application.initialize() and Application.start()
  - Register webhook URL with Telegram (skip in dev if webhook_url unset)

Shutdown:
  - Application.stop() + Application.shutdown()

Route:
  - POST /bot/{webhook_secret} → Application.update_queue.put(Update.de_json(...))
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from telegram import Update
from telegram.ext import Application

from app.core.config import AppConfig, Secrets

if TYPE_CHECKING:
    from app.api.deps import AppState

logger = logging.getLogger(__name__)

router = APIRouter(tags=["bot"])


def build_application(secrets: Secrets) -> Application:
    if not secrets.bot_token:
        raise RuntimeError("BOT_TOKEN not configured; cannot start bot")
    return Application.builder().token(secrets.bot_token).updater(None).build()


async def start_application(app: Application) -> None:
    await app.initialize()
    await app.start()


async def stop_application(app: Application) -> None:
    try:
        await app.stop()
    finally:
        await app.shutdown()


async def register_handlers(app: Application, state: AppState) -> None:
    """Attach all bot command/message handlers."""
    from app.bot import handlers as h

    h.install(app, state)


@router.post("/bot/{webhook_secret}")
async def bot_webhook(webhook_secret: str, request: Request) -> dict:
    from app.api.deps import get_state

    state = get_state(request)
    if not state.secrets.webhook_secret or webhook_secret != state.secrets.webhook_secret:
        raise HTTPException(status_code=403, detail="invalid_webhook_secret")

    bot_app = getattr(request.app.state, "bot_app", None)
    if bot_app is None:
        raise HTTPException(status_code=503, detail="bot_not_ready")

    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    if update is None:
        raise HTTPException(status_code=400, detail="invalid_update")
    await bot_app.process_update(update)
    return {"ok": True}


def public_webhook_url(config: AppConfig, secrets: Secrets) -> str | None:
    """Construct webhook URL from config. Returns None when no base URL is set
    (we still accept incoming webhooks, but we won't ask Telegram to deliver to us)."""
    base = getattr(config, "public_base_url", None)
    if not base or not secrets.webhook_secret:
        return None
    return f"{base.rstrip('/')}/bot/{secrets.webhook_secret}"
