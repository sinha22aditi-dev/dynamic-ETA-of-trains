from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, func, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK


class User(Base):
    __tablename__ = "users"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    preferred_language = Column(String(8), default="en", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    tracked_trains = relationship("TrackedTrain", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    smart_alarms = relationship("SmartAlarm", back_populates="user", cascade="all, delete-orphan")
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")


class NotificationPreferences(Base):
    __tablename__ = "notification_preferences"

    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    delay_alerts = Column(Boolean, default=True, nullable=False)
    eta_change_alerts = Column(Boolean, default=True, nullable=False)
    approaching_destination_alerts = Column(Boolean, default=True, nullable=False)
    min_delay_change_threshold_mins = Column(Integer, default=5, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="notification_preferences")
