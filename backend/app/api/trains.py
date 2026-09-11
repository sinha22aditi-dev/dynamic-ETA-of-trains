from typing import Optional, List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, desc
from datetime import datetime, timezone

from app.database import get_db
from app.dependencies import get_optional_current_user
from app.models.train import Train, Route, RouteStation
from app.models.position import TrainPosition, TrainRunningStatus
from app.models.prediction import Prediction
from app.models.user import User
from app.services import prediction_service
from app.clients import ml_client
from app.clients.ml_client import MLUnavailableError

router = APIRouter(prefix="/trains", tags=["trains"])


@router.get("", response_model=dict)
async def search_trains(
    query: Optional[str] = Query(None, description="Train name or ID prefix"),
    origin: Optional[str] = Query(None),
    destination: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Search trains by name, ID, or origin/destination stations."""
    stmt = select(Train)
    if query:
        # Match by name (case-insensitive) or exact ID
        try:
            tid = int(query)
            stmt = stmt.where(or_(
                Train.train_id == tid,
                Train.train_name.ilike(f"%{query}%"),
            ))
        except ValueError:
            stmt = stmt.where(Train.train_name.ilike(f"%{query}%"))

    if origin or destination:
        stmt = stmt.join(Train.routes)
        if origin:
            stmt = stmt.where(Route.origin_station == origin.upper())
        if destination:
            stmt = stmt.where(Route.destination_station == destination.upper())

    count_stmt = select(Train)
    if query:
        try:
            tid = int(query)
            count_stmt = count_stmt.where(or_(
                Train.train_id == tid,
                Train.train_name.ilike(f"%{query}%"),
            ))
        except ValueError:
            count_stmt = count_stmt.where(Train.train_name.ilike(f"%{query}%"))

    result = await db.execute(stmt.order_by(Train.train_id).limit(limit).offset(offset))
    trains = result.scalars().all()

    items = []
    for t in trains:
        # Get first route for origin/destination
        route_result = await db.execute(
            select(Route).where(Route.train_id == t.train_id).limit(1)
        )
        route = route_result.scalar_one_or_none()
        items.append({
            "train_id": t.train_id,
            "train_name": t.train_name,
            "train_type": t.train_type,
            "train_category": t.train_category,
            "railway_zone": t.railway_zone,
            "origin_station": route.origin_station if route else None,
            "destination_station": route.destination_station if route else None,
        })

    return {"total": len(items), "offset": offset, "limit": limit, "items": items}


@router.get("/{train_id}", response_model=dict)
async def get_train_detail(train_id: int, db: AsyncSession = Depends(get_db)):
    """Get train static information including route."""
    train = await db.get(Train, train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {train_id} not found."}}
        )

    route_result = await db.execute(
        select(Route).where(Route.train_id == train_id).limit(1)
    )
    route = route_result.scalar_one_or_none()

    route_data = None
    if route:
        stations_result = await db.execute(
            select(RouteStation).where(RouteStation.route_id == route.id).order_by(RouteStation.stop_order)
        )
        route_stations = stations_result.scalars().all()
        route_data = {
            "id": route.id,
            "origin_station": route.origin_station,
            "destination_station": route.destination_station,
            "direction": route.direction,
            "scheduled_distance_km": float(route.scheduled_distance_km) if route.scheduled_distance_km else None,
            "scheduled_journey_time_hrs": float(route.scheduled_journey_time_hrs) if route.scheduled_journey_time_hrs else None,
            "stations": [
                {
                    "station_code": rs.station_code,
                    "stop_order": rs.stop_order,
                    "scheduled_halt_time_mins": rs.scheduled_halt_time_mins,
                }
                for rs in route_stations
            ]
        }

    return {
        "train_id": train.train_id,
        "train_name": train.train_name,
        "train_type": train.train_type,
        "train_category": train.train_category,
        "railway_zone": train.railway_zone,
        "route": route_data,
    }


@router.get("/{train_id}/status", response_model=dict)
async def get_train_status(
    train_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    Get live train status including latest position and ML prediction.
    Returns degraded=true if ML is unavailable (serves last cached prediction).
    """
    train = await db.get(Train, train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {train_id} not found."}}
        )

    # Get latest position
    pos_result = await db.execute(
        select(TrainPosition)
        .where(TrainPosition.train_id == train_id)
        .order_by(desc(TrainPosition.observed_at))
        .limit(1)
    )
    position = pos_result.scalar_one_or_none()

    # Get running status
    running_status = await db.get(TrainRunningStatus, train_id)

    # Try to get a fresh prediction
    degraded = False
    prediction = None

    if position:
        try:
            fresh_prediction = await prediction_service.run_prediction(db, train_id, position, train)
            if fresh_prediction:
                prediction = fresh_prediction
        except Exception:
            pass

    if prediction is None:
        # Fall back to cached prediction
        prediction = await prediction_service.get_latest_prediction(db, train_id)
        if prediction:
            degraded = prediction_service.is_stale(prediction)

    # Compute ETA delta from previous prediction
    eta_delta = None
    if prediction:
        prev_result = await db.execute(
            select(Prediction)
            .where(Prediction.train_id == train_id)
            .where(Prediction.id != prediction.id)
            .order_by(desc(Prediction.created_at))
            .limit(1)
        )
        prev = prev_result.scalar_one_or_none()
        if prev and prev.eta and prediction.eta:
            old_eta = prev.eta
            new_eta = prediction.eta
            if old_eta.tzinfo is None:
                old_eta = old_eta.replace(tzinfo=timezone.utc)
            if new_eta.tzinfo is None:
                new_eta = new_eta.replace(tzinfo=timezone.utc)
            eta_delta = (new_eta - old_eta).total_seconds() / 60

    pos_data = _position_to_dict(position)
    pred_data = _prediction_to_dict(prediction)

    return {
        "train_id": train_id,
        "train_name": train.train_name,
        "position": pos_data,
        "prediction": pred_data,
        "eta_delta_from_previous_mins": eta_delta,
        "degraded": degraded,
        "journey_status": running_status.journey_status if running_status else None,
        "last_synced_at": running_status.last_synced_at.isoformat() if running_status and running_status.last_synced_at else None,
    }


@router.post("/{train_id}/predict", response_model=dict)
async def predict_now(
    train_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Force a fresh prediction for a train (on-demand, from the latest position)."""
    train = await db.get(Train, train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {train_id} not found."}}
        )

    pos_result = await db.execute(
        select(TrainPosition)
        .where(TrainPosition.train_id == train_id)
        .order_by(desc(TrainPosition.observed_at))
        .limit(1)
    )
    position = pos_result.scalar_one_or_none()

    if not position:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NO_POSITION", "message": "No position data available for this train yet."}}
        )

    prediction = await prediction_service.run_prediction(db, train_id, position, train, force=True)
    if not prediction:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "PREDICTION_UNAVAILABLE", "message": "ML service is unavailable."}}
        )

    return _prediction_to_dict(prediction)


def _position_to_dict(pos: Optional[TrainPosition]) -> Optional[dict]:
    if not pos:
        return None
    return {
        "id": pos.id,
        "train_id": pos.train_id,
        "observed_at": pos.observed_at.isoformat() if pos.observed_at else None,
        "current_station": pos.current_station,
        "previous_station": pos.previous_station,
        "next_station": pos.next_station,
        "latitude": float(pos.latitude) if pos.latitude else None,
        "longitude": float(pos.longitude) if pos.longitude else None,
        "current_speed_kmh": float(pos.current_speed_kmh) if pos.current_speed_kmh else None,
        "current_delay_mins": float(pos.current_delay_mins) if pos.current_delay_mins else None,
        "distance_remaining_km": float(pos.distance_remaining_km) if pos.distance_remaining_km else None,
        "movement_status": pos.movement_status,
    }


def _prediction_to_dict(pred: Optional[Prediction]) -> Optional[dict]:
    if not pred:
        return None
    conf = float(pred.delay_reason_confidence) if pred.delay_reason_confidence else None
    return {
        "id": pred.id,
        "train_id": pred.train_id,
        "model_used": pred.model_used,
        "current_delay_mins": float(pred.current_delay_mins) if pred.current_delay_mins else None,
        "predicted_additional_delay_mins": float(pred.predicted_additional_delay_mins) if pred.predicted_additional_delay_mins else None,
        "predicted_total_delay_mins": float(pred.predicted_total_delay_mins) if pred.predicted_total_delay_mins else None,
        "estimated_remaining_travel_mins": float(pred.estimated_remaining_travel_mins) if pred.estimated_remaining_travel_mins else None,
        "eta": pred.eta.isoformat() if pred.eta else None,
        "eta_lower": pred.eta_lower.isoformat() if pred.eta_lower else None,
        "eta_upper": pred.eta_upper.isoformat() if pred.eta_upper else None,
        "delay_reason": pred.delay_reason,
        "delay_reason_confidence": conf,
        "delay_reason_confidence_pct": round(conf * 100, 1) if conf else None,
        "propagation_probability": float(pred.propagation_probability) if pred.propagation_probability else None,
        "propagation_risk": pred.propagation_risk,
        "created_at": pred.created_at.isoformat() if pred.created_at else None,
        "stale": prediction_service.is_stale(pred),
    }
