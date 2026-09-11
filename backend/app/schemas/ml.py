from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class MLPredictRequest(BaseModel):
    """Exact shape the ML /predict endpoint expects."""
    data: Dict[str, Any]
    history: List[Dict[str, Any]] = []


class MLPredictResponse(BaseModel):
    """Exact shape of the ML /predict response (§12.2)."""
    current_delay_mins: float
    predicted_additional_delay_mins: float
    predicted_total_delay_mins: float
    estimated_remaining_travel_mins: float
    eta: str
    eta_interval: Dict[str, str]  # {"lower": "...", "upper": "..."}
    delay_reason: str
    delay_reason_confidence: float
    propagation: Dict[str, Any]  # {"probability": float, "risk": str}


class MLTemporalRequest(BaseModel):
    data: Dict[str, Any] = {}
    history: List[Dict[str, Any]]


class MLTemporalResponse(BaseModel):
    gru_predicted_additional_delay_mins: float
    hybrid_gnn_gru_predicted_additional_delay_mins: float


class MLChatRequest(BaseModel):
    query: str
    prediction: Dict[str, Any]  # must be the raw /predict response dict
    language: str = "en"


class MLChatResponse(BaseModel):
    language: str
    response: str
