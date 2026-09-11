from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.tracking import TrackedTrain
from app.models.train import Train, Route
from app.models.prediction import Prediction
from app.schemas.requests import TrackTrainRequest
from app.services import prediction_service
from sqlalchemy import desc

router = APIRouter(prefix="/tracking", tags=["tracking"])


@router.get("", response_model=dict)
async def list_tracked_trains(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrackedTrain).where(TrackedTrain.user_id == current_user.id)
    )
    tracked = result.scalars().all()

    items = []
    for t in tracked:
        train = await db.get(Train, t.train_id)
        if not train:
            continue
        route_result = await db.execute(
            select(Route).where(Route.train_id == t.train_id).limit(1)
        )
        route = route_result.scalar_one_or_none()
        latest_pred = await prediction_service.get_latest_prediction(db, t.train_id)

        items.append({
            "id": t.id,
            "train_id": train.train_id,
            "train_name": train.train_name,
            "train_type": train.train_type,
            "train_category": train.train_category,
            "origin_station": route.origin_station if route else None,
            "destination_station": route.destination_station if route else None,
            "target_station_code": t.target_station_code,
            "created_at": t.created_at.isoformat(),
            "latest_prediction": _pred_to_dict(latest_pred) if latest_pred else None,
        })

    return {"total": len(items), "items": items}


@router.post("", response_model=dict, status_code=201)
async def track_train(
    body: TrackTrainRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    train = await db.get(Train, body.train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {body.train_id} not found."}}
        )

    try:
        tracked = TrackedTrain(
            user_id=current_user.id,
            train_id=body.train_id,
            target_station_code=body.target_station_code,
        )
        db.add(tracked)
        await db.commit()
        await db.refresh(tracked)
        return {"id": tracked.id, "train_id": tracked.train_id, "message": "Train tracked successfully."}
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "ALREADY_TRACKED", "message": "You are already tracking this train."}}
        )


@router.delete("/{tracking_id}", status_code=204)
async def untrack_train(
    tracking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tracked = await db.get(TrackedTrain, tracking_id)
    if not tracked or tracked.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Tracked entry not found."}}
        )
    await db.delete(tracked)
    await db.commit()


def _pred_to_dict(pred: Optional[Prediction]) -> Optional[dict]:
    if not pred:
        return None
    conf = float(pred.delay_reason_confidence) if pred.delay_reason_confidence else None
    return {
        "id": pred.id,
        "eta": pred.eta.isoformat() if pred.eta else None,
        "predicted_total_delay_mins": float(pred.predicted_total_delay_mins) if pred.predicted_total_delay_mins else None,
        "delay_reason": pred.delay_reason,
        "delay_reason_confidence_pct": round(conf * 100, 1) if conf else None,
        "propagation_risk": pred.propagation_risk,
        "stale": prediction_service.is_stale(pred),
        "created_at": pred.created_at.isoformat() if pred.created_at else None,
    }
