from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    preferred_language: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class StationResponse(BaseModel):
    code: str
    display_name: Optional[str]
    graph_node_index: int

    model_config = {"from_attributes": True}


class RouteStationResponse(BaseModel):
    station_code: str
    stop_order: int
    scheduled_halt_time_mins: Optional[int]
    scheduled_arrival_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RouteSegmentResponse(BaseModel):
    from_station: str
    to_station: str
    distance_km: Optional[float]

    model_config = {"from_attributes": True}


class RouteResponse(BaseModel):
    id: int
    train_id: int
    origin_station: Optional[str]
    destination_station: Optional[str]
    direction: Optional[str]
    scheduled_distance_km: Optional[float]
    scheduled_journey_time_hrs: Optional[float]
    stations: List[RouteStationResponse] = []
    segments: List[RouteSegmentResponse] = []

    model_config = {"from_attributes": True}


class TrainSummaryResponse(BaseModel):
    train_id: int
    train_name: str
    train_type: str
    train_category: str
    railway_zone: str
    origin_station: Optional[str] = None
    destination_station: Optional[str] = None

    model_config = {"from_attributes": True}


class TrainDetailResponse(BaseModel):
    train_id: int
    train_name: str
    train_type: str
    train_category: str
    railway_zone: str
    route: Optional[RouteResponse] = None

    model_config = {"from_attributes": True}


class PositionResponse(BaseModel):
    id: int
    train_id: int
    sequence_id: Optional[str]
    sequence_step: Optional[int]
    observed_at: datetime
    current_station: Optional[str]
    previous_station: Optional[str]
    next_station: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    current_speed_kmh: Optional[float]
    current_delay_mins: Optional[float]
    distance_remaining_km: Optional[float]
    movement_status: Optional[str]

    model_config = {"from_attributes": True}


class PredictionResponse(BaseModel):
    id: int
    train_id: int
    model_used: str
    current_delay_mins: Optional[float]
    predicted_additional_delay_mins: Optional[float]
    predicted_total_delay_mins: Optional[float]
    estimated_remaining_travel_mins: Optional[float]
    eta: datetime
    eta_lower: Optional[datetime]
    eta_upper: Optional[datetime]
    delay_reason: Optional[str]
    delay_reason_confidence: Optional[float]
    # UI: present as "Delay Reason Confidence %" per PRD §36 rec
    delay_reason_confidence_pct: Optional[float] = None
    propagation_probability: Optional[float]
    propagation_risk: Optional[str]
    created_at: datetime
    stale: bool = False  # computed at response time

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class TrainStatusResponse(BaseModel):
    position: Optional[PositionResponse]
    prediction: Optional[PredictionResponse]
    delta_vs_schedule_mins: Optional[float]  # eta - scheduled_arrival (display only)
    eta_delta_from_previous_mins: Optional[float]  # latest eta - previous eta
    eta_stale: bool = False
    degraded: bool = False  # ML unavailable, serving cached prediction
    journey_status: Optional[str] = None
    last_synced_at: Optional[datetime] = None


class NotificationResponse(BaseModel):
    id: int
    train_id: int
    type: str
    title: str
    body: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferencesResponse(BaseModel):
    user_id: int
    delay_alerts: bool
    eta_change_alerts: bool
    approaching_destination_alerts: bool
    min_delay_change_threshold_mins: int

    model_config = {"from_attributes": True}


class AlarmResponse(BaseModel):
    id: int
    train_id: int
    target_station_code: str
    offset_minutes: int
    auto_adjust: bool
    is_active: bool
    last_evaluated_eta: Optional[datetime]
    triggered_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class TrackedTrainResponse(BaseModel):
    id: int
    train_id: int
    train_name: str
    train_type: str
    origin_station: Optional[str]
    destination_station: Optional[str]
    target_station_code: Optional[str]
    latest_prediction: Optional[PredictionResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    db: str


class MLHealthResponse(BaseModel):
    ml_status: str
    models: Optional[List[str]] = None


class ReplayStatusResponse(BaseModel):
    running: bool
    current_step: Optional[int]
    total_sequences: int
    tick_seconds: int
