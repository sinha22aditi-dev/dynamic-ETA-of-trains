# Import all models so Alembic can detect them
from app.models.user import User, NotificationPreferences
from app.models.train import Station, Train, Route, RouteStation, RouteSegment, TrainSchedule
from app.models.position import ReplaySource, TrainPosition, TrainRunningStatus
from app.models.prediction import Prediction
from app.models.tracking import TrackedTrain
from app.models.notification import Notification
from app.models.alarm import SmartAlarm

__all__ = [
    "User", "NotificationPreferences",
    "Station", "Train", "Route", "RouteStation", "RouteSegment", "TrainSchedule",
    "ReplaySource", "TrainPosition", "TrainRunningStatus",
    "Prediction",
    "TrackedTrain",
    "Notification",
    "SmartAlarm",
]
