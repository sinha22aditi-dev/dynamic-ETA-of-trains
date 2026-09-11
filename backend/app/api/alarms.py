from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.alarm import SmartAlarm
from app.models.train import Train, Station
from app.schemas.requests import CreateAlarmRequest, UpdateAlarmRequest

router = APIRouter(prefix="/alarms", tags=["alarms"])


@router.get("", response_model=dict)
async def list_alarms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SmartAlarm).where(SmartAlarm.user_id == current_user.id)
    )
    alarms = result.scalars().all()
    return {
        "total": len(alarms),
        "items": [_alarm_dict(a) for a in alarms]
    }


@router.post("", response_model=dict, status_code=201)
async def create_alarm(
    body: CreateAlarmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    train = await db.get(Train, body.train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {body.train_id} not found."}}
        )
    station = await db.get(Station, body.target_station_code)
    if not station:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "STATION_NOT_FOUND", "message": f"Station {body.target_station_code} not found."}}
        )

    alarm = SmartAlarm(
        user_id=current_user.id,
        train_id=body.train_id,
        target_station_code=body.target_station_code,
        offset_minutes=body.offset_minutes,
        auto_adjust=body.auto_adjust,
        is_active=True,
    )
    db.add(alarm)
    await db.commit()
    await db.refresh(alarm)
    return _alarm_dict(alarm)


@router.get("/{alarm_id}", response_model=dict)
async def get_alarm(
    alarm_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alarm = await db.get(SmartAlarm, alarm_id)
    if not alarm or alarm.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALARM_NOT_FOUND", "message": "Alarm not found."}}
        )
    return _alarm_dict(alarm)


@router.patch("/{alarm_id}", response_model=dict)
async def update_alarm(
    alarm_id: int,
    body: UpdateAlarmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alarm = await db.get(SmartAlarm, alarm_id)
    if not alarm or alarm.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALARM_NOT_FOUND", "message": "Alarm not found."}}
        )

    if body.offset_minutes is not None:
        alarm.offset_minutes = body.offset_minutes
    if body.auto_adjust is not None:
        alarm.auto_adjust = body.auto_adjust
    if body.is_active is not None:
        alarm.is_active = body.is_active

    await db.commit()
    await db.refresh(alarm)
    return _alarm_dict(alarm)


@router.delete("/{alarm_id}", status_code=204)
async def delete_alarm(
    alarm_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alarm = await db.get(SmartAlarm, alarm_id)
    if not alarm or alarm.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "ALARM_NOT_FOUND", "message": "Alarm not found."}}
        )
    await db.delete(alarm)
    await db.commit()


def _alarm_dict(alarm: SmartAlarm) -> dict:
    return {
        "id": alarm.id,
        "train_id": alarm.train_id,
        "target_station_code": alarm.target_station_code,
        "offset_minutes": alarm.offset_minutes,
        "auto_adjust": alarm.auto_adjust,
        "is_active": alarm.is_active,
        "last_evaluated_eta": alarm.last_evaluated_eta.isoformat() if alarm.last_evaluated_eta else None,
        "triggered_at": alarm.triggered_at.isoformat() if alarm.triggered_at else None,
        "created_at": alarm.created_at.isoformat(),
    }
