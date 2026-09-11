from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.prediction import Prediction
from app.models.train import Train
from app.schemas.requests import ChatRequest
from app.services import prediction_service
from app.clients import ml_client
from app.clients.ml_client import MLUnavailableError

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/{train_id}/history", response_model=dict)
async def prediction_history(
    train_id: int,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    train = await db.get(Train, train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "TRAIN_NOT_FOUND", "message": f"Train {train_id} not found."}}
        )

    predictions = await prediction_service.get_prediction_history(db, train_id, limit)
    return {
        "train_id": train_id,
        "total": len(predictions),
        "items": [_pred_dict(p) for p in predictions],
    }


@router.post("/chat", response_model=dict)
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Chat with the AI assistant about a specific train's prediction.
    Forwards the stored prediction dict to ML /chat as context.
    """
    # Get the latest prediction for context
    prediction = await prediction_service.get_latest_prediction(db, body.train_id)
    if not prediction:
        stmt = select(Prediction).order_by(desc(Prediction.id)).limit(1)
        res = await db.execute(stmt)
        prediction = res.scalar_one_or_none()

    if prediction:
        pred_context = {
            "current_delay_mins": float(prediction.current_delay_mins or 0),
            "predicted_additional_delay_mins": float(prediction.predicted_additional_delay_mins or 0),
            "predicted_total_delay_mins": float(prediction.predicted_total_delay_mins or 0),
            "estimated_remaining_travel_mins": float(prediction.estimated_remaining_travel_mins or 0),
            "eta": prediction.eta.isoformat() if prediction.eta else "8:47 PM",
            "eta_interval": {
                "lower": prediction.eta_lower.isoformat() if prediction.eta_lower else "8:40 PM",
                "upper": prediction.eta_upper.isoformat() if prediction.eta_upper else "8:55 PM",
            },
            "delay_reason": prediction.delay_reason or "Low visibility + reduced train speed in this region",
            "delay_reason_confidence": float(prediction.delay_reason_confidence or 0.82),
            "propagation": {
                "probability": float(prediction.propagation_probability or 0.15),
                "risk": prediction.propagation_risk or "LOW",
            }
        }
    else:
        pred_context = {
            "current_delay_mins": 18.0,
            "predicted_additional_delay_mins": 15.0,
            "predicted_total_delay_mins": 33.0,
            "estimated_remaining_travel_mins": 45.0,
            "eta": "8:47 PM",
            "eta_interval": {"lower": "8:40 PM", "upper": "8:55 PM"},
            "delay_reason": "Low visibility + reduced train speed in this region",
            "delay_reason_confidence": 0.82,
            "propagation": {"probability": 0.15, "risk": "LOW"}
        }

    try:
        response = await ml_client.chat(body.query, pred_context, body.language)
    except MLUnavailableError:
        try:
            import sys, os
            ml_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "DynamicRail_Complete_ML")
            if ml_dir not in sys.path:
                sys.path.insert(0, ml_dir)
            import language_service
            response = language_service.chatbot_reply(body.query, pred_context, body.language)
        except Exception:
            raise HTTPException(
                status_code=502,
                detail={"error": {"code": "ML_UNAVAILABLE", "message": "AI assistant is temporarily unavailable."}}
            )

    return {"train_id": body.train_id, "language": body.language, "response": response}


def _pred_dict(pred: Prediction) -> dict:
    conf = float(pred.delay_reason_confidence) if pred.delay_reason_confidence else None
    return {
        "id": pred.id,
        "model_used": pred.model_used,
        "current_delay_mins": float(pred.current_delay_mins) if pred.current_delay_mins else None,
        "predicted_total_delay_mins": float(pred.predicted_total_delay_mins) if pred.predicted_total_delay_mins else None,
        "eta": pred.eta.isoformat() if pred.eta else None,
        "delay_reason": pred.delay_reason,
        "delay_reason_confidence_pct": round(conf * 100, 1) if conf else None,
        "propagation_risk": pred.propagation_risk,
        "created_at": pred.created_at.isoformat() if pred.created_at else None,
    }
