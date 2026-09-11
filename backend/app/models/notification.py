from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Text, ForeignKey, func, Index
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False)
    type = Column(String(32), nullable=False)  # delay_increase, eta_change, approaching_destination, alarm_triggered
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    related_prediction_id = Column(BigInteger, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="notifications")
    train = relationship("Train")
    related_prediction = relationship("Prediction", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )
