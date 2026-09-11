from sqlalchemy import Column, BigInteger, String, DateTime, Numeric, Integer, ForeignKey, func, Index, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK, JSONType


class ReplaySource(Base):
    """Stores the full sequential CSV for the replay engine. Never exposed as live data."""
    __tablename__ = "replay_source"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    train_id = Column(BigInteger, nullable=False, index=True)
    sequence_id = Column(String(20), nullable=False)
    sequence_step = Column(Integer, nullable=False)
    raw_data = Column(JSONType, nullable=False)  # full row as JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_replay_source_seq", "sequence_id", "sequence_step"),
    )


class TrainPosition(Base):
    """Live-feeling position, written by the replay engine each tick."""
    __tablename__ = "train_positions"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False)
    sequence_id = Column(String(20), nullable=True)
    sequence_step = Column(Integer, nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    current_station = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=True)
    previous_station = Column(String(10), nullable=True)
    next_station = Column(String(10), nullable=True)
    latitude = Column(Numeric(10, 6), nullable=True)
    longitude = Column(Numeric(10, 6), nullable=True)
    current_location_km = Column(Numeric(10, 2), nullable=True)
    current_speed_kmh = Column(Numeric(6, 2), nullable=True)
    current_delay_mins = Column(Numeric(8, 2), nullable=True)
    distance_remaining_km = Column(Numeric(10, 2), nullable=True)
    movement_status = Column(String(32), nullable=True)
    stoppage_duration_mins = Column(Integer, nullable=True)
    raw_snapshot = Column(JSONType, nullable=False, default=dict)  # all 78 XGBoost features
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    train = relationship("Train", back_populates="positions")
    predictions = relationship("Prediction", back_populates="position")

    __table_args__ = (
        Index("ix_train_positions_train_observed", "train_id", "observed_at"),
    )


class TrainRunningStatus(Base):
    """Denormalized latest state per train for fast reads."""
    __tablename__ = "train_running_status"

    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), primary_key=True)
    current_position_id = Column(BigInteger, ForeignKey("train_positions.id", ondelete="SET NULL"), nullable=True)
    journey_status = Column(String(16), nullable=True)
    last_prediction_id = Column(BigInteger, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    train = relationship("Train", back_populates="running_status")
    current_position = relationship("TrainPosition", foreign_keys=[current_position_id])
    last_prediction = relationship("Prediction", foreign_keys=[last_prediction_id])
