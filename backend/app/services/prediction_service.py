"""
Prediction Service — orchestrates the full prediction pipeline per PRD §13.

Flow:
  get position → build 78-field ML payload (excluding all leakage fields)
  → call ML /predict → validate response → persist prediction
  → update train_running_status → return prediction
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.prediction import Prediction
from app.models.position import TrainPosition, TrainRunningStatus
from app.models.train import Train, TrainSchedule, RouteStation
from app.clients import ml_client
from app.clients.ml_client import MLUnavailableError, MLBadRequestError

logger = logging.getLogger(__name__)

# The 30-station graph universe — station codes outside this set must be defaulted
VALID_STATION_CODES = {
    "ADI", "AGC", "ALD", "ASN", "BCT", "BPL", "BRC", "BZA", "CNB", "CSTM",
    "DHN", "GAYA", "GWL", "HWH", "JHS", "JP", "KOTA", "LKO", "MAS", "MGS",
    "NDLS", "NGP", "PNBE", "PUNE", "RTM", "SBC", "SC", "ST", "TDL", "VAPI"
}

# Staleness threshold: 2× replay tick interval (PRD §14)
STALE_THRESHOLD_MINUTES = 20


def _safe_station(code: Optional[str]) -> str:
    """Return the station code if in the 30-node graph, else default 'NDLS'."""
    if code and code in VALID_STATION_CODES:
        return code
    if code:
        logger.warning(f"Station code '{code}' outside 30-node graph, defaulting to NDLS")
    return "NDLS"


def _build_ml_payload(position: TrainPosition, train: Train) -> Dict[str, Any]:
    """
    Build the 78-field ML request payload from the train position snapshot.
    Never includes any leakage/target fields (enforced by ml_client.LEAKAGE_FIELDS).
    """
    snapshot = dict(position.raw_snapshot or {})

    # Override with live columnar fields (authoritative source)
    snapshot["train_name"] = train.train_name
    snapshot["train_type"] = train.train_type
    snapshot["train_category"] = train.train_category
    snapshot["railway_zone"] = train.railway_zone

    snapshot["current_station"] = _safe_station(position.current_station)
    snapshot["previous_station"] = _safe_station(position.previous_station) if position.previous_station else "NDLS"
    snapshot["next_station"] = _safe_station(position.next_station) if position.next_station else "NDLS"

    snapshot["latitude"] = float(position.latitude or 0)
    snapshot["longitude"] = float(position.longitude or 0)
    snapshot["current_location_km"] = float(position.current_location_km or 0)
    snapshot["current_speed_kmh"] = float(position.current_speed_kmh or 0)
    snapshot["current_delay_mins"] = float(position.current_delay_mins or 0)
    snapshot["distance_remaining_km"] = float(position.distance_remaining_km or 0)
    snapshot["movement_status"] = position.movement_status or "Running"
    snapshot["stoppage_duration_mins"] = int(position.stoppage_duration_mins or 0)

    # Timestamp for ETA calculation — always send it (PRD §12.1)
    if position.observed_at:
        snapshot["timestamp"] = position.observed_at.isoformat()
    else:
        snapshot["timestamp"] = datetime.now(timezone.utc).isoformat()

    # Fill in required fields that might be missing from snapshot with safe defaults
    defaults = {
        "section_id": snapshot.get("section_id", "S001"),
        "track_id": snapshot.get("track_id", "T001"),
        "distance_to_next_station_km": snapshot.get("distance_to_next_station_km", 50.0),
        "distance_from_previous_station_km": snapshot.get("distance_from_previous_station_km", 30.0),
        "direction": snapshot.get("direction", "Up"),
        "scheduled_journey_time_hrs": snapshot.get("scheduled_journey_time_hrs", 12.0),
        "scheduled_segment_travel_time_mins": snapshot.get("scheduled_segment_travel_time_mins", 90.0),
        "scheduled_distance_km": snapshot.get("scheduled_distance_km", 1000.0),
        "station_halt_time_mins": snapshot.get("station_halt_time_mins", 5),
        "previous_station_delay": snapshot.get("previous_station_delay", 0.0),
        "delay_2_stations_ago": snapshot.get("delay_2_stations_ago", 0.0),
        "delay_3_stations_ago": snapshot.get("delay_3_stations_ago", 0.0),
        "historical_avg_train_delay": snapshot.get("historical_avg_train_delay", 5.0),
        "historical_avg_station_delay": snapshot.get("historical_avg_station_delay", 4.0),
        "historical_avg_section_delay": snapshot.get("historical_avg_section_delay", 3.0),
        "historical_on_time_pct": snapshot.get("historical_on_time_pct", 0.75),
        "historical_segment_travel_time_mins": snapshot.get("historical_segment_travel_time_mins", 85.0),
        "train_ahead_delay_mins": snapshot.get("train_ahead_delay_mins", 0.0),
        "train_ahead_speed_kmh": snapshot.get("train_ahead_speed_kmh", 80.0),
        "train_ahead_distance_km": snapshot.get("train_ahead_distance_km", 20.0),
        "number_of_trains_ahead": snapshot.get("number_of_trains_ahead", 0),
        "distance_between_trains_km": snapshot.get("distance_between_trains_km", 20.0),
        "headway_mins": snapshot.get("headway_mins", 15.0),
        "same_track": snapshot.get("same_track", False),
        "same_section": snapshot.get("same_section", False),
        "section_congestion_index": snapshot.get("section_congestion_index", 0.3),
        "delay_reason_code": snapshot.get("delay_reason_code", "NO_DELAY"),
        "reason_severity": snapshot.get("reason_severity", "Low"),
        "reason_duration_mins": snapshot.get("reason_duration_mins", 0),
        "confirmed_unconfirmed_reason": snapshot.get("confirmed_unconfirmed_reason", "Not_Applicable"),
        "reason_source": snapshot.get("reason_source", "Not_Applicable"),
        "temperature_celsius": snapshot.get("temperature_celsius", 25.0),
        "rainfall_mm": snapshot.get("rainfall_mm", 0.0),
        "humidity_pct": snapshot.get("humidity_pct", 50.0),
        "wind_speed_kmh": snapshot.get("wind_speed_kmh", 10.0),
        "visibility_meters": snapshot.get("visibility_meters", 5000.0),
        "weather_condition": snapshot.get("weather_condition", "Clear"),
        "weather_severity": snapshot.get("weather_severity", "None"),
        "track_condition": snapshot.get("track_condition", "Good"),
        "track_vibration_hz": snapshot.get("track_vibration_hz", 2.0),
        "rail_wear_mm": snapshot.get("rail_wear_mm", 1.0),
        "speed_restriction_kmh": snapshot.get("speed_restriction_kmh", 110.0),
        "track_maintenance_active": snapshot.get("track_maintenance_active", False),
        "signal_status": snapshot.get("signal_status", "Green"),
        "section_capacity_pct": snapshot.get("section_capacity_pct", 0.5),
        "bearing_temperature_c": snapshot.get("bearing_temperature_c", 45.0),
        "axle_temperature_c": snapshot.get("axle_temperature_c", 40.0),
        "brake_condition": snapshot.get("brake_condition", "Good"),
        "brake_pressure_bar": snapshot.get("brake_pressure_bar", 5.0),
        "brake_pad_wear_pct": snapshot.get("brake_pad_wear_pct", 20.0),
        "maintenance_status": snapshot.get("maintenance_status", "Up_to_Date"),
        "days_since_maintenance": snapshot.get("days_since_maintenance", 30),
        "sensor_health": snapshot.get("sensor_health", "Healthy"),
        "failure_type": snapshot.get("failure_type", "No_Failure"),
        "failure_severity": snapshot.get("failure_severity", "No_Failure"),
        "hour": snapshot.get("hour", datetime.now().hour),
        "day_of_week": snapshot.get("day_of_week", datetime.now().weekday()),
        "month": snapshot.get("month", datetime.now().month),
        "season": snapshot.get("season", "Winter"),
        "is_weekend_holiday": snapshot.get("is_weekend_holiday", False),
        "is_peak_hour": snapshot.get("is_peak_hour", False),
        "journey_status": snapshot.get("journey_status", "In_Transit"),
        "estimated_remaining_travel_time_mins": snapshot.get("estimated_remaining_travel_time_mins", 120.0),
    }

    for k, v in defaults.items():
        if k not in snapshot or snapshot[k] is None:
            snapshot[k] = v

    return snapshot


async def run_prediction(
    db: AsyncSession,
    train_id: int,
    position: TrainPosition,
    train: Train,
    force: bool = False,
) -> Optional[Prediction]:
    """
    Full prediction pipeline for a single train position.
    Returns the newly created Prediction or None if ML failed and no cached fallback.
    Caller gets degraded=True info from the calling endpoint layer.
    """
    # Check if this position already has a prediction (avoid duplicates, unless forced)
    if not force:
        existing = await db.execute(
            select(Prediction)
            .where(Prediction.position_id == position.id)
            .limit(1)
        )
        if existing.scalar_one_or_none():
            return None  # already predicted for this position

    # Validate station before calling ML
    station_code = position.current_station
    if station_code and station_code not in VALID_STATION_CODES:
        logger.warning(f"Train {train_id} at unknown station '{station_code}', clamping to NDLS for ML call")

    payload = _build_ml_payload(position, train)
    requested_at = datetime.now(timezone.utc)

    try:
        ml_response = await ml_client.predict(payload)
        responded_at = datetime.now(timezone.utc)
        logger.info(f"ML /predict OK for train {train_id}, ETA={ml_response.get('eta')}")
    except MLBadRequestError as e:
        logger.error(f"ML rejected payload for train {train_id} (backend bug): {e}")
        return None
    except MLUnavailableError as e:
        logger.warning(f"ML unavailable for train {train_id}: {e}")
        return None

    # Parse and persist the prediction
    try:
        from datetime import datetime as dt
        import dateutil.parser

        def parse_dt(s):
            if not s:
                return None
            try:
                return dateutil.parser.parse(s)
            except Exception:
                return None

        eta = parse_dt(ml_response["eta"])
        if eta is None:
            logger.error(f"Could not parse eta from ML response: {ml_response.get('eta')}")
            return None

        eta_lower = parse_dt(ml_response.get("eta_interval", {}).get("lower"))
        eta_upper = parse_dt(ml_response.get("eta_interval", {}).get("upper"))
        prop = ml_response.get("propagation", {})

        # Get metrics snapshot (internal/audit only)
        try:
            metrics_snap = await _get_ml_metrics()
        except Exception:
            metrics_snap = None

        prediction = Prediction(
            train_id=train_id,
            position_id=position.id,
            model_used="xgboost",
            current_delay_mins=ml_response.get("current_delay_mins"),
            predicted_additional_delay_mins=ml_response.get("predicted_additional_delay_mins"),
            predicted_total_delay_mins=ml_response.get("predicted_total_delay_mins"),
            estimated_remaining_travel_mins=ml_response.get("estimated_remaining_travel_mins"),
            eta=eta,
            eta_lower=eta_lower,
            eta_upper=eta_upper,
            delay_reason=ml_response.get("delay_reason"),
            delay_reason_confidence=ml_response.get("delay_reason_confidence"),
            propagation_probability=prop.get("probability"),
            propagation_risk=prop.get("risk"),
            ml_metrics_snapshot=metrics_snap,
            requested_at=requested_at,
            responded_at=responded_at,
        )
        db.add(prediction)
        await db.flush()  # get the ID

        # Update running status
        status = await db.get(TrainRunningStatus, train_id)
        if status:
            status.last_prediction_id = prediction.id
            status.last_synced_at = datetime.now(timezone.utc)
        else:
            status = TrainRunningStatus(
                train_id=train_id,
                current_position_id=position.id,
                last_prediction_id=prediction.id,
                last_synced_at=datetime.now(timezone.utc),
            )
            db.add(status)

        await db.commit()
        await db.refresh(prediction)
        return prediction

    except Exception as e:
        logger.error(f"Error persisting prediction for train {train_id}: {e}")
        await db.rollback()
        return None


async def get_latest_prediction(db: AsyncSession, train_id: int) -> Optional[Prediction]:
    """Get the most recent prediction for a train."""
    result = await db.execute(
        select(Prediction)
        .where(Prediction.train_id == train_id)
        .order_by(desc(Prediction.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_prediction_history(db: AsyncSession, train_id: int, limit: int = 20):
    """Get the N most recent predictions for a train."""
    result = await db.execute(
        select(Prediction)
        .where(Prediction.train_id == train_id)
        .order_by(desc(Prediction.created_at))
        .limit(limit)
    )
    return result.scalars().all()


def is_stale(prediction: Prediction) -> bool:
    """Check if a prediction is older than the staleness threshold."""
    if not prediction or not prediction.created_at:
        return True
    now = datetime.now(timezone.utc)
    created = prediction.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age_minutes = (now - created).total_seconds() / 60
    return age_minutes > STALE_THRESHOLD_MINUTES


async def _get_ml_metrics() -> Optional[dict]:
    """Fetch current ML metrics for audit snapshot. Internal use only."""
    try:
        import httpx
        from app.config import settings
        async with httpx.AsyncClient(base_url=settings.ML_SERVICE_URL, timeout=2.0) as client:
            resp = await client.get("/metrics")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return None
