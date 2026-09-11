from fastapi import HTTPException
from typing import Optional, Any


def error_response(code: str, message: str, details: Optional[Any] = None, http_status: int = 400) -> HTTPException:
    """Return a standardized error HTTPException per PRD §23."""
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


class DynamicRailError(Exception):
    """Base application error."""
    def __init__(self, code: str, message: str, http_status: int = 400, details: Any = None):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details
        super().__init__(message)

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=self.http_status,
            detail={"error": {"code": self.code, "message": self.message, "details": self.details}},
        )


class TrainNotFoundError(DynamicRailError):
    def __init__(self, train_id: Any):
        super().__init__("TRAIN_NOT_FOUND", f"Train {train_id} was not found.", 404)


class StationNotFoundError(DynamicRailError):
    def __init__(self, code: Any):
        super().__init__("STATION_NOT_FOUND", f"Station {code} was not found.", 404)


class AlarmNotFoundError(DynamicRailError):
    def __init__(self, alarm_id: Any):
        super().__init__("ALARM_NOT_FOUND", f"Alarm {alarm_id} was not found.", 404)


class PredictionUnavailableError(DynamicRailError):
    def __init__(self, message: str = "Prediction unavailable. ML service may be down."):
        super().__init__("PREDICTION_UNAVAILABLE", message, 502)


class UnauthorizedError(DynamicRailError):
    def __init__(self, message: str = "Authentication required."):
        super().__init__("UNAUTHORIZED", message, 401)


class ForbiddenError(DynamicRailError):
    def __init__(self, message: str = "Access denied."):
        super().__init__("FORBIDDEN", message, 403)
