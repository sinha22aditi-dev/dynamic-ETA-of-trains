from sqlalchemy import Column, BigInteger, String, DateTime, Numeric, ForeignKey, func, Index, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK, JSONType


class Prediction(Base):
    """Append-only prediction history. Never updated in place."""
    __tablename__ = "predictions"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False)
    position_id = Column(BigInteger, ForeignKey("train_positions.id", ondelete="RESTRICT"), nullable=False)
    model_used = Column(String(24), nullable=False, default="xgboost")

    # ML response fields — exact names from /predict response (§12.2)
    current_delay_mins = Column(Numeric(8, 2), nullable=True)
    predicted_additional_delay_mins = Column(Numeric(8, 2), nullable=True)
    predicted_total_delay_mins = Column(Numeric(8, 2), nullable=True)
    estimated_remaining_travel_mins = Column(Numeric(8, 2), nullable=True)
    eta = Column(DateTime(timezone=True), nullable=False)
    eta_lower = Column(DateTime(timezone=True), nullable=True)
    eta_upper = Column(DateTime(timezone=True), nullable=True)
    delay_reason = Column(Text, nullable=True)
    delay_reason_confidence = Column(Numeric(4, 3), nullable=True)
    propagation_probability = Column(Numeric(5, 4), nullable=True)
    propagation_risk = Column(String(8), nullable=True)  # LOW/MEDIUM/HIGH

    # ML metrics snapshot at prediction time — internal/audit only
    ml_metrics_snapshot = Column(JSONType, nullable=True)

    requested_at = Column(DateTime(timezone=True), nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    train = relationship("Train", back_populates="predictions")
    position = relationship("TrainPosition", back_populates="predictions")
    notifications = relationship("Notification", back_populates="related_prediction")

    __table_args__ = (
        Index("ix_predictions_train_created", "train_id", "created_at"),
    )
