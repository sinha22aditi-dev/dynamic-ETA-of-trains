from sqlalchemy import Column, BigInteger, String, DateTime, Numeric, Integer, UniqueConstraint, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base, BigIntPK


class Station(Base):
    __tablename__ = "stations"

    code = Column(String(10), primary_key=True)
    graph_node_index = Column(Integer, unique=True, nullable=False)
    display_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    route_stations = relationship("RouteStation", back_populates="station", foreign_keys="RouteStation.station_code")


class Train(Base):
    __tablename__ = "trains"

    train_id = Column(BigInteger, primary_key=True)
    train_name = Column(String(255), nullable=False, index=True)
    train_type = Column(String(32), nullable=False)
    train_category = Column(String(32), nullable=False)
    railway_zone = Column(String(8), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    routes = relationship("Route", back_populates="train", cascade="all, delete-orphan")
    positions = relationship("TrainPosition", back_populates="train")
    running_status = relationship("TrainRunningStatus", back_populates="train", uselist=False)
    tracked_by = relationship("TrackedTrain", back_populates="train")
    predictions = relationship("Prediction", back_populates="train")


class Route(Base):
    __tablename__ = "routes"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False, index=True)
    origin_station = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=True)
    destination_station = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=True)
    direction = Column(String(4), nullable=True)
    scheduled_distance_km = Column(Numeric(10, 2), nullable=True)
    scheduled_journey_time_hrs = Column(Numeric(6, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    train = relationship("Train", back_populates="routes")
    route_stations = relationship("RouteStation", back_populates="route", order_by="RouteStation.stop_order", cascade="all, delete-orphan")
    schedules = relationship("TrainSchedule", back_populates="route", cascade="all, delete-orphan")


class RouteStation(Base):
    __tablename__ = "route_stations"
    __table_args__ = (UniqueConstraint("route_id", "stop_order"),)

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    route_id = Column(BigInteger, ForeignKey("routes.id", ondelete="CASCADE"), nullable=False, index=True)
    station_code = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=False)
    stop_order = Column(Integer, nullable=False)
    scheduled_halt_time_mins = Column(Integer, nullable=True)

    route = relationship("Route", back_populates="route_stations")
    station = relationship("Station", back_populates="route_stations", foreign_keys=[station_code])
    schedules = relationship("TrainSchedule", back_populates="route_station", cascade="all, delete-orphan")


class RouteSegment(Base):
    __tablename__ = "route_segments"
    __table_args__ = (UniqueConstraint("from_station", "to_station"),)

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    from_station = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=False)
    to_station = Column(String(10), ForeignKey("stations.code", ondelete="RESTRICT"), nullable=False)
    distance_km = Column(Numeric(10, 3), nullable=True)
    observed_count = Column(Integer, nullable=True)


class TrainSchedule(Base):
    __tablename__ = "train_schedules"

    id = Column(BigIntPK, primary_key=True, autoincrement=True)
    train_id = Column(BigInteger, ForeignKey("trains.train_id", ondelete="RESTRICT"), nullable=False, index=True)
    route_id = Column(BigInteger, ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    route_station_id = Column(BigInteger, ForeignKey("route_stations.id", ondelete="CASCADE"), nullable=False)
    scheduled_arrival_time = Column(DateTime(timezone=True), nullable=True)
    scheduled_departure_time = Column(DateTime(timezone=True), nullable=True)

    route = relationship("Route", back_populates="schedules")
    route_station = relationship("RouteStation", back_populates="schedules")
