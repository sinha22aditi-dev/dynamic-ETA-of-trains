"""
DynamicRail Backend — FastAPI Application Entry Point

Architecture (PRD §7):
- FastAPI with async SQLAlchemy (asyncpg + PostgreSQL)
- APScheduler for replay ticks (every REPLAY_TICK_SECONDS)
- All routes prefixed /api/v1
"""

import logging
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import engine
from app.models import *  # noqa — ensure all models are imported for metadata
from app.api import auth, trains, stations, tracking, predictions, notifications, alarms, health, passthrough, replay
from app.services.replay_service import replay_engine

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("DynamicRail backend starting up...")

    # Initialize the replay engine (loads sequence index from DB)
    try:
        await replay_engine.initialize()
        logger.info("Replay engine initialized.")
    except Exception as e:
        logger.warning(f"Replay engine initialization failed (DB may be empty): {e}")

    # Schedule the replay tick job
    scheduler.add_job(
        replay_engine.tick,
        "interval",
        seconds=settings.REPLAY_TICK_SECONDS,
        id="replay_tick",
        max_instances=1,
        coalesce=True,
    )

    # Start replay automatically
    try:
        await replay_engine.start()
        scheduler.start()
        logger.info(f"Replay engine started (tick every {settings.REPLAY_TICK_SECONDS}s).")
    except Exception as e:
        logger.warning(f"Replay engine auto-start failed: {e}")

    yield

    # Shutdown
    logger.info("DynamicRail backend shutting down...")
    if scheduler.running:
        scheduler.shutdown(wait=False)
    await engine.dispose()


app = FastAPI(
    title="DynamicRail API",
    description="Dynamic ETA prediction for Indian Railways — SIH26028",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler — standardized error envelope
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An internal error occurred.", "details": str(exc)}},
    )

# Register routers under /api/v1
PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(trains.router, prefix=PREFIX)
app.include_router(stations.router, prefix=PREFIX)
app.include_router(tracking.router, prefix=PREFIX)
app.include_router(predictions.router, prefix=PREFIX)
app.include_router(notifications.router, prefix=PREFIX)
app.include_router(alarms.router, prefix=PREFIX)
app.include_router(health.router)  # /health, /health/ml, /health/replay
app.include_router(passthrough.router, prefix=PREFIX)
app.include_router(replay.router, prefix=PREFIX)

import os
from fastapi.responses import FileResponse, HTMLResponse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_HTML = os.path.join(ROOT_DIR, "frontend.html")
STYLES_CSS = os.path.join(ROOT_DIR, "styles.css")


@app.get("/", response_model=None)
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and os.path.exists(FRONTEND_HTML):
        return FileResponse(FRONTEND_HTML, media_type="text/html")
    return {
        "service": "DynamicRail API",
        "version": "2.0.0",
        "problem": "SIH26028",
        "docs": "/api/docs",
        "app": "/app",
    }


@app.get("/app", response_class=FileResponse)
async def serve_app():
    if os.path.exists(FRONTEND_HTML):
        return FileResponse(FRONTEND_HTML, media_type="text/html")
    return HTMLResponse("<h1>DynamicRail Frontend</h1><p>frontend.html not found</p>", status_code=404)


@app.get("/styles.css", response_class=FileResponse)
async def serve_styles():
    if os.path.exists(STYLES_CSS):
        return FileResponse(STYLES_CSS, media_type="text/css")
    return HTMLResponse("/* styles.css not found */", status_code=404)

