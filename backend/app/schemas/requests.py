from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: Optional[str] = None


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TrackTrainRequest(BaseModel):
    train_id: int
    target_station_code: Optional[str] = None


class CreateAlarmRequest(BaseModel):
    train_id: int
    target_station_code: str
    offset_minutes: int = Field(default=10)
    auto_adjust: bool = True


class UpdateAlarmRequest(BaseModel):
    offset_minutes: Optional[int] = None
    auto_adjust: Optional[bool] = None
    is_active: Optional[bool] = None


class ChatRequest(BaseModel):
    train_id: int
    query: str
    language: str = "en"


class NotificationPreferencesRequest(BaseModel):
    delay_alerts: Optional[bool] = None
    eta_change_alerts: Optional[bool] = None
    approaching_destination_alerts: Optional[bool] = None
    min_delay_change_threshold_mins: Optional[int] = None
