"""
Alarm Service — evaluates smart alarms after each new prediction.

Logic (PRD §19):
- A smart alarm fires when: now + offset_minutes >= ETA of target_station
- For MVP, target_station alarm fires when train ETA ≤ offset_minutes from now
- One-fire gate: once fired (triggered_at set), the alarm does not re-fire
- auto_adjust: every prediction updates last_evaluated_eta to reflect new ETA
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.alarm import SmartAlarm
from app.models.prediction import Prediction
from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def evaluate_alarms(
    db: AsyncSession,
    train_id: int,
    new_prediction: Prediction,
):
    """
    Evaluate all active alarms for this train.
    Called after every new prediction is committed.
    """
    if not new_prediction.eta:
        return

    result = await db.execute(
        select(SmartAlarm)
        .where(SmartAlarm.train_id == train_id)
        .where(SmartAlarm.is_active == True)
        .where(SmartAlarm.triggered_at == None)  # not yet fired
    )
    alarms = result.scalars().all()

    now = datetime.now(timezone.utc)
    eta = new_prediction.eta
    if eta.tzinfo is None:
        eta = eta.replace(tzinfo=timezone.utc)

    for alarm in alarms:
        # Update last_evaluated_eta if auto_adjust is on
        if alarm.auto_adjust:
            alarm.last_evaluated_eta = eta

        # Alarm fires when ETA is within offset_minutes from now
        fire_at = eta - timedelta(minutes=alarm.offset_minutes)
        if now >= fire_at:
            alarm.triggered_at = now
            alarm.is_active = False

            # Create a notification for the user
            train_name = await _get_train_name(db, train_id)
            station_code = alarm.target_station_code
            notif = Notification(
                user_id=alarm.user_id,
                train_id=train_id,
                type="alarm_triggered",
                title=f"Alarm: {train_name}",
                body=f"Your alarm fired! Train arrives at {station_code} in ~{alarm.offset_minutes} min (ETA: {eta.strftime('%H:%M')}).",
                is_read=False,
                related_prediction_id=new_prediction.id,
            )
            db.add(notif)
            logger.info(f"Alarm {alarm.id} fired for user {alarm.user_id} train {train_id}")

    await db.commit()


async def _get_train_name(db: AsyncSession, train_id: int) -> str:
    from app.models.train import Train
    train = await db.get(Train, train_id)
    return train.train_name if train else str(train_id)
