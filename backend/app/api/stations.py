from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.train import Station

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get("", response_model=dict)
async def list_stations(
    db: AsyncSession = Depends(get_db),
    q: str = Query(None, description="Filter by code or display name"),
):
    stmt = select(Station).order_by(Station.code)
    if q:
        stmt = stmt.where(
            Station.code.ilike(f"%{q}%") | Station.display_name.ilike(f"%{q}%")
        )
    result = await db.execute(stmt)
    stations = result.scalars().all()
    return {
        "total": len(stations),
        "items": [
            {
                "code": s.code,
                "display_name": s.display_name or s.code,
                "graph_node_index": s.graph_node_index,
            }
            for s in stations
        ]
    }


@router.get("/{code}", response_model=dict)
async def get_station(code: str, db: AsyncSession = Depends(get_db)):
    station = await db.get(Station, code.upper())
    if not station:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "STATION_NOT_FOUND", "message": f"Station {code} not found."}}
        )
    return {
        "code": station.code,
        "display_name": station.display_name or station.code,
        "graph_node_index": station.graph_node_index,
    }
