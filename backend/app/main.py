"""FastAPI app entrypoint: wires middleware, routers, and lifespan state."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_router
from app.api import chats as chats_router
from app.api import deps
from app.api import download as download_router
from app.api import fs as fs_router
from app.api import preview as preview_router
from app.api import settings as settings_router
from app.bot import webhook as bot_webhook
from app.core.acl import ACL
from app.core.auth import LoginManager
from app.core.client_pool import ClientPool
from app.core.config import load_config, load_secrets
from app.core.downloader import Downloader
from app.core.keyframe_extractor import KeyframeExtractor
from app.core.queue import JobQueue
from app.core.session_store import SessionStore
from app.miniapp import routes as miniapp_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    config = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
    config.ensure_dirs()
    secrets = load_secrets()

    store = SessionStore(config, secrets.session_encryption_key)
    store.cleanup_all_live()

    pool = ClientPool(config, secrets, store)
    acl = ACL(config)
    login_manager = LoginManager(config, secrets, store, pool, acl)
    downloader = Downloader(config, pool)
    keyframes = KeyframeExtractor(config, pool)
    queue = JobQueue(
        snapshot_path=config.queue_file,
        num_workers=config.concurrency.per_user,
    )
    queue.set_handler(downloader.run_job)

    state = deps.AppState(
        config=config,
        secrets=secrets,
        session_store=store,
        client_pool=pool,
        acl=acl,
        login_manager=login_manager,
        queue=queue,
        downloader=downloader,
        keyframes=keyframes,
    )
    app.state.app_state = state

    await queue.start()
    pool.start_reaper()

    # Optional: start Telegram Bot (P2) when BOT_TOKEN is configured.
    bot_app = None
    if secrets.bot_token:
        try:
            bot_app = bot_webhook.build_application(secrets)
            await bot_webhook.register_handlers(bot_app, state)
            await bot_webhook.start_application(bot_app)
            app.state.bot_app = bot_app
            url = bot_webhook.public_webhook_url(config, secrets)
            if url:
                await bot_app.bot.set_webhook(
                    url=url,
                    drop_pending_updates=True,
                    allowed_updates=["message", "callback_query"],
                )
                logger.info("bot webhook registered: %s", url)
            else:
                logger.info(
                    "bot started but no public_base_url; incoming webhook route active anyway"
                )
        except Exception:
            logger.exception("bot startup failed; continuing without bot")
            bot_app = None

    logger.info(
        "app started (mode=%s, download_dir=%s, bot=%s)",
        config.deployment_mode,
        config.download_dir,
        "on" if bot_app else "off",
    )

    try:
        yield
    finally:
        logger.info("shutting down")
        if bot_app is not None:
            await bot_webhook.stop_application(bot_app)
        await queue.stop()
        await pool.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="Telegram Media DL", version="0.1.0", lifespan=lifespan)

    config = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router)
    app.include_router(chats_router.router)
    app.include_router(preview_router.router)
    app.include_router(download_router.router)
    app.include_router(fs_router.router)
    app.include_router(settings_router.router)
    app.include_router(bot_webhook.router)
    miniapp_routes.mount(app)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
