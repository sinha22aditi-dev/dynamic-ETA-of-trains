"""
ML Client — the ONLY place the backend calls the DynamicRail ML service.

Respects:
- Exact endpoint contract from PRD §12 and api.py inspection
- No ML logic is re-implemented here
- Timeout + retry policy from PRD §13
- Graceful error handling: ML unavailable → raises MLUnavailableError
- Never exposes ML endpoints directly (all calls are server-to-server)
"""

import logging
from typing import Any, Dict, Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

# Fields that MUST NEVER be sent to /predict — leakage/targets per PRD §5.6 and config.XGB_DROP
LEAKAGE_FIELDS = {
    "predicted_eta", "actual_arrival_time", "future_additional_delay_mins",
    "future_delay_20m", "future_delay_target", "propagation_delay_mins",
    "propagation_occurred", "propagation_probability",
    "remaining_travel_time_mins",  # derived output, distinct from estimated_remaining_travel_time_mins
    "sequence_step", "sequence_id", "split", "data_source",
    "train_id", "train_ahead_id",
    # Time columns excluded from features
    "scheduled_arrival_time", "scheduled_departure_time", "reason_start_time",
    # Text label output from ML rule engine, not a live input feature
    "delay_reason_category",
}


class MLUnavailableError(Exception):
    """ML service is unavailable or returned an unrecoverable error."""
    pass


class MLBadRequestError(Exception):
    """ML service returned 400 (malformed payload) — backend bug, not transient."""
    pass


def _strip_leakage(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove any leakage/target fields before sending to ML service."""
    return {k: v for k, v in data.items() if k not in LEAKAGE_FIELDS}


def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.ML_SERVICE_URL,
        timeout=settings.ML_SERVICE_TIMEOUT_SECONDS,
    )


async def predict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call POST /predict with the 78-field feature snapshot.
    Returns the raw ML response dict.
    Raises MLUnavailableError or MLBadRequestError on failure.
    """
    clean_data = _strip_leakage(data)
    payload = {"data": clean_data, "history": []}

    last_error: Optional[Exception] = None
    for attempt in range(2):  # one retry on timeout/connection error only
        try:
            async with _get_client() as client:
                logger.debug(f"ML /predict attempt {attempt + 1}")
                resp = await client.post("/predict", json=payload)

                if resp.status_code == 400:
                    msg = f"ML /predict returned 400 (backend built malformed payload): {resp.text[:300]}"
                    logger.error(msg)
                    raise MLBadRequestError(msg)

                if resp.status_code != 200:
                    raise MLUnavailableError(f"ML /predict returned {resp.status_code}: {resp.text[:200]}")

                result = resp.json()
                _validate_predict_response(result)
                return result

        except MLBadRequestError:
            raise  # never retry on 400
        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(f"ML /predict timeout on attempt {attempt + 1}")
            if attempt == 0:
                continue  # retry once
        except httpx.ConnectError as e:
            last_error = e
            logger.warning(f"ML /predict connection error: {e}")
            break  # no point retrying a connection refused

    raise MLUnavailableError(f"ML /predict failed after retries: {last_error}")


def _validate_predict_response(result: Dict[str, Any]) -> None:
    """Validate required fields are present in ML response."""
    required = {"current_delay_mins", "predicted_additional_delay_mins",
                "predicted_total_delay_mins", "estimated_remaining_travel_mins",
                "eta", "eta_interval", "delay_reason", "delay_reason_confidence", "propagation"}
    missing = required - set(result.keys())
    if missing:
        raise MLUnavailableError(f"ML /predict response missing required fields: {missing}")

    # Validate eta is parseable
    try:
        import pandas as pd
        ts = pd.to_datetime(result["eta"])
        if pd.isna(ts):
            raise ValueError("eta is NaT")
    except Exception as e:
        raise MLUnavailableError(f"ML /predict returned unparseable eta: {e}")

    # Validate confidence in range
    conf = result.get("delay_reason_confidence", 0)
    if not (0.0 <= float(conf) <= 1.0):
        logger.warning(f"ML response delay_reason_confidence out of range: {conf}")

    # Validate propagation structure
    prop = result.get("propagation", {})
    if "probability" not in prop or "risk" not in prop:
        raise MLUnavailableError("ML /predict propagation field malformed")


async def predict_temporal(history: list) -> Dict[str, Any]:
    """
    Call POST /predict/temporal with ≥6 history snapshots.
    Returns GRU and Hybrid GNN-GRU delay predictions (not ETAs).
    Raises MLUnavailableError if < 6 history entries or service down.
    """
    if len(history) < 6:
        raise MLUnavailableError("predict/temporal requires ≥6 history entries")

    payload = {"data": {}, "history": history}
    try:
        async with _get_client() as client:
            resp = await client.post("/predict/temporal", json=payload)
            if resp.status_code != 200:
                raise MLUnavailableError(f"ML /predict/temporal returned {resp.status_code}")
            return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise MLUnavailableError(f"ML /predict/temporal unavailable: {e}")


async def chat(query: str, prediction: Dict[str, Any], language: str = "en") -> str:
    """
    Call POST /chat — forwards the exact stored /predict response as context.
    Returns the chatbot response string.
    """
    payload = {"query": query, "prediction": prediction, "language": language}
    try:
        async with _get_client() as client:
            resp = await client.post("/chat", json=payload)
            if resp.status_code != 200:
                raise MLUnavailableError(f"ML /chat returned {resp.status_code}")
            return resp.json().get("response", "")
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise MLUnavailableError(f"ML /chat unavailable: {e}")


async def get_weather(lat: float, lon: float) -> Dict[str, Any]:
    """Proxy GET /weather to ML service."""
    try:
        async with _get_client() as client:
            resp = await client.get("/weather", params={"lat": lat, "lon": lon})
            if resp.status_code != 200:
                raise MLUnavailableError(f"ML /weather returned {resp.status_code}")
            return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise MLUnavailableError(f"ML /weather unavailable: {e}")


async def get_directions(origin: str, destination: str, travelmode: str = "transit") -> Dict[str, Any]:
    """Proxy GET /maps/directions to ML service."""
    try:
        async with _get_client() as client:
            resp = await client.get(
                "/maps/directions",
                params={"origin": origin, "destination": destination, "travelmode": travelmode}
            )
            if resp.status_code != 200:
                raise MLUnavailableError(f"ML /maps/directions returned {resp.status_code}")
            return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise MLUnavailableError(f"ML /maps/directions unavailable: {e}")


async def get_languages() -> list:
    """Proxy GET /languages to ML service."""
    try:
        async with _get_client() as client:
            resp = await client.get("/languages")
            if resp.status_code != 200:
                raise MLUnavailableError(f"ML /languages returned {resp.status_code}")
            return resp.json()
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise MLUnavailableError(f"ML /languages unavailable: {e}")


async def health_check() -> Dict[str, Any]:
    """Check ML service health."""
    try:
        async with _get_client() as client:
            resp = await client.get("/health")
            if resp.status_code != 200:
                return {"status": "error", "models": []}
            return resp.json()
    except Exception as e:
        logger.warning(f"ML health check failed: {e}")
        return {"status": "unavailable", "models": []}
