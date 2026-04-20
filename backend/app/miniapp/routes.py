"""Serve the frontend build under /app for Telegram Mini App usage.

The frontend detects a `Telegram.WebApp` host at runtime and switches auth
from QR / phone to initData exchange. A single bundle covers both use cases.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

router = APIRouter(tags=["miniapp"])


def frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


def mount(app: FastAPI) -> None:
    dist = frontend_dist_dir()
    if not dist.exists():
        logger.info("frontend/dist not built; Mini App route disabled")
        return

    # SPA fallback — return index.html for unknown sub-paths so client-side
    # routing keeps working when users hit the Mini App via deep links.
    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    async def miniapp_index() -> FileResponse:
        index = dist / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="index_not_built")
        return FileResponse(index, media_type="text/html")

    # Serve assets with long cache; index.html stays short-cache via the route above.
    app.mount("/app/assets", StaticFiles(directory=dist / "assets"), name="miniapp_assets")
    logger.info("miniapp static mounted from %s", dist)
