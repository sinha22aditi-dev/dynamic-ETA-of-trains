from fastapi import APIRouter, Depends, HTTPException, Query
from app.clients import ml_client
from app.clients.ml_client import MLUnavailableError

router = APIRouter(tags=["passthrough"])


@router.get("/weather", response_model=dict)
async def weather(lat: float = Query(...), lon: float = Query(...)):
    """Proxy weather request to ML service. ML service handles the API call."""
    try:
        return await ml_client.get_weather(lat, lon)
    except MLUnavailableError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "ML_UNAVAILABLE", "message": str(e)}}
        )


@router.get("/directions", response_model=dict)
async def directions(origin: str = Query(...), destination: str = Query(...), travelmode: str = Query("transit")):
    """Proxy directions request to ML service (returns Google Maps URL)."""
    try:
        return await ml_client.get_directions(origin, destination, travelmode)
    except MLUnavailableError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "ML_UNAVAILABLE", "message": str(e)}}
        )


@router.get("/languages", response_model=list)
async def languages():
    """Return list of supported languages from ML service."""
    try:
        return await ml_client.get_languages()
    except MLUnavailableError:
        # Return sensible fallback
        return [{"code": "en", "name": "English"}, {"code": "hi", "name": "Hindi"}]
