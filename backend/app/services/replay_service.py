"""
Replay Service — drives the virtual clock over the sequential dataset.

Uses PRD §11.2 Mode 1 (pre-seeded, timestamp-driven replay):
- Sequential rows already loaded into replay_source table
- Maintains per-sequence pointer (current step)
- On each tick: advance pointer, write train_positions row, fire prediction
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.position import ReplaySource, TrainPosition, TrainRunningStatus
from app.models.train import Train
from app.services import prediction_service
from app.services import notification_service, alarm_service
from app.config import settings

logger = logging.getLogger(__name__)


class ReplayEngine:
    """
    Manages the virtual clock and per-sequence step pointers.
    All state is in-memory (pointers) + database (positions/predictions).
    """

    def __init__(self):
        self._running: bool = False
        self._paused: bool = False
        # Per sequence_id: current step index
        self._pointers: Dict[str, int] = {}
        self._sequences: list = []  # ordered list of (sequence_id, train_id)
        self._initialized: bool = False
        self._current_global_step: int = 0
        self._total_sequences: int = 0
        self._tick_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Load sequence/train mapping from DB. Called at app startup."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ReplaySource.sequence_id, ReplaySource.train_id)
                .distinct()
                .order_by(ReplaySource.sequence_id)
            )
            rows = result.all()
            self._sequences = [(r.sequence_id, r.train_id) for r in rows]
            self._total_sequences = len(self._sequences)
            # Start all sequences at step 0
            for seq_id, _ in self._sequences:
                self._pointers[seq_id] = 0
            self._initialized = True
            logger.info(f"Replay engine initialized: {self._total_sequences} sequences")

    async def start(self):
        """Begin advancing the virtual clock."""
        if not self._initialized:
            await self.initialize()
        if self._running and not self._paused:
            return
        self._running = True
        self._paused = False
        logger.info("Replay engine started")

    async def pause(self):
        self._paused = True
        logger.info("Replay engine paused")

    async def resume(self):
        self._paused = False
        logger.info("Replay engine resumed")

    async def reset(self):
        """Rewind all sequences to step 0."""
        for seq_id in self._pointers:
            self._pointers[seq_id] = 0
        self._current_global_step = 0
        self._paused = False
        logger.info("Replay engine reset to step 0")

    def status(self) -> dict:
        return {
            "running": self._running and not self._paused,
            "paused": self._paused,
            "current_step": self._current_global_step,
            "total_sequences": self._total_sequences,
            "tick_seconds": settings.REPLAY_TICK_SECONDS,
        }

    async def tick(self):
        """
        Advance one step for every sequence.
        For each sequence that advances, write a new train_positions row and fire prediction.
        """
        if not self._running or self._paused:
            return

        self._current_global_step += 1
        active_trains: Set[int] = set()

        async with AsyncSessionLocal() as db:
            for seq_id, train_id in self._sequences:
                current_step = self._pointers[seq_id]

                # Fetch the row for this step
                result = await db.execute(
                    select(ReplaySource)
                    .where(ReplaySource.sequence_id == seq_id)
                    .where(ReplaySource.sequence_step == current_step)
                    .limit(1)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    # Sequence exhausted — loop back to 0
                    self._pointers[seq_id] = 0
                    continue

                # Advance pointer for next tick
                self._pointers[seq_id] = current_step + 1

                # Write the train_positions row
                data = dict(row.raw_data)
                try:
                    pos = TrainPosition(
                        train_id=train_id,
                        sequence_id=seq_id,
                        sequence_step=current_step,
                        observed_at=_parse_dt(data.get("timestamp")) or datetime.now(timezone.utc),
                        current_station=_safe_str(data.get("current_station")),
                        previous_station=_safe_str(data.get("previous_station")),
                        next_station=_safe_str(data.get("next_station")),
                        latitude=_safe_float(data.get("latitude")),
                        longitude=_safe_float(data.get("longitude")),
                        current_location_km=_safe_float(data.get("current_location_km")),
                        current_speed_kmh=_safe_float(data.get("current_speed_kmh")),
                        current_delay_mins=_safe_float(data.get("current_delay_mins")),
                        distance_remaining_km=_safe_float(data.get("distance_remaining_km")),
                        movement_status=_safe_str(data.get("movement_status")),
                        stoppage_duration_mins=_safe_int(data.get("stoppage_duration_mins")),
                        raw_snapshot=data,
                    )
                    db.add(pos)
                    await db.flush()

                    # Update running status
                    status = await db.get(TrainRunningStatus, train_id)
                    if status:
                        status.current_position_id = pos.id
                        status.journey_status = _safe_str(data.get("journey_status"))
                        status.last_synced_at = datetime.now(timezone.utc)
                    else:
                        status = TrainRunningStatus(
                            train_id=train_id,
                            current_position_id=pos.id,
                            journey_status=_safe_str(data.get("journey_status")),
                            last_synced_at=datetime.now(timezone.utc),
                        )
                        db.add(status)

                    await db.commit()
                    active_trains.add(train_id)

                    # Fire prediction for this train (async, don't block tick)
                    asyncio.create_task(
                        _fire_prediction_and_evaluate(train_id, pos.id)
                    )

                except Exception as e:
                    logger.error(f"Replay tick error for seq {seq_id} step {current_step}: {e}")
                    await db.rollback()

        logger.debug(f"Replay tick {self._current_global_step}: advanced {len(active_trains)} trains")


async def _fire_prediction_and_evaluate(train_id: int, position_id: int):
    """Background task: run prediction + notification/alarm evaluation for one train."""
    async with AsyncSessionLocal() as db:
        try:
            train = await db.get(Train, train_id)
            position = await db.get(TrainPosition, position_id)
            if not train or not position:
                return

            prediction = await prediction_service.run_prediction(db, train_id, position, train)
            if prediction:
                # Evaluate notifications and alarms
                await notification_service.evaluate_notifications(db, train_id, prediction)
                await alarm_service.evaluate_alarms(db, train_id, prediction)
        except Exception as e:
            logger.error(f"Prediction/evaluation error for train {train_id}: {e}")


# Singleton instance
replay_engine = ReplayEngine()


def _parse_dt(val) -> Optional[datetime]:
    if not val:
        return None
    try:
        import pandas as pd
        ts = pd.to_datetime(val, utc=True)
        return ts.to_pydatetime()
    except Exception:
        return None


def _safe_str(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and val != val):
        return None
    return str(val).strip() or None


def _safe_float(val) -> Optional[float]:
    try:
        v = float(val)
        return None if v != v else v  # nan check
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None
