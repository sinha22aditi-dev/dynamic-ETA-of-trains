from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, check_db_connection
from app.clients import ml_client

router = APIRouter(tags=["health"])


@router.get("/health", response_model=dict)
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
    }


@router.get("/health/ml", response_model=dict)
async def ml_health():
    result = await ml_client.health_check()
    return {
        "ml_status": result.get("status", "unknown"),
        "models": result.get("models", []),
    }


@router.get("/health/replay", response_model=dict)
async def replay_health():
    from app.services.replay_service import replay_engine
    return replay_engine.status()
