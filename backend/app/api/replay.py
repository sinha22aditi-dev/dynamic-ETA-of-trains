from fastapi import APIRouter, HTTPException
from app.services.replay_service import replay_engine

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/status", response_model=dict)
async def status():
    return replay_engine.status()


@router.post("/start", response_model=dict)
async def start():
    await replay_engine.start()
    return {"message": "Replay engine started.", **replay_engine.status()}


@router.post("/pause", response_model=dict)
async def pause():
    await replay_engine.pause()
    return {"message": "Replay engine paused.", **replay_engine.status()}


@router.post("/resume", response_model=dict)
async def resume():
    await replay_engine.resume()
    return {"message": "Replay engine resumed.", **replay_engine.status()}


@router.post("/reset", response_model=dict)
async def reset():
    await replay_engine.reset()
    return {"message": "Replay engine reset.", **replay_engine.status()}
