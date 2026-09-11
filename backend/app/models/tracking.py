from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK


class TrackedTrain(Base):
    __tablename__ = "tracked_trains"
    __table_args__ = (UniqueConstraint("user_id", "train_id"),)

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False)
    target_station_code = Column(String(10), ForeignKey("stations.code", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="tracked_trains")
    train = relationship("Train", back_populates="tracked_by")
    target_station = relationship("Station", foreign_keys=[target_station_code])
