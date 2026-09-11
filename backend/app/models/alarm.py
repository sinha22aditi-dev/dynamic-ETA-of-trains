from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Integer, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK


class SmartAlarm(Base):
    __tablename__ = "smart_alarms"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False)
    target_station_code = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=False)
    offset_minutes = Column(Integer, nullable=False)  # minutes before ETA to trigger
    auto_adjust = Column(Boolean, default=True, nullable=False)  # recalculate on every ETA update
    is_active = Column(Boolean, default=True, nullable=False)
    last_evaluated_eta = Column(DateTime(timezone=True), nullable=True)
    triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="smart_alarms")
    train = relationship("Train")
    target_station = relationship("Station", foreign_keys=[target_station_code])

    __table_args__ = (
        Index("ix_smart_alarms_train_active", "train_id", "is_active"),
    )
