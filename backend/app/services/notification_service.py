"""
Notification Service — evaluates conditions and creates notifications for tracked trains.

Rules (PRD §18):
- delay_increase: predicted_total_delay_mins increased by ≥ threshold since last notification
- eta_change: ETA shifted by ≥ threshold mins
- approaching_destination: distance_remaining_km ≤ APPROACHING_DESTINATION_KM

Cooldown: one notification per type per train per 15 minutes per user.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.notification import Notification
from app.models.tracking import TrackedTrain
from app.models.prediction import Prediction
from app.models.position import TrainPosition
from app.models.user import NotificationPreferences
from app.config import settings

logger = logging.getLogger(__name__)

COOLDOWN_MINUTES = 15


async def evaluate_notifications(
    db: AsyncSession,
    train_id: int,
    new_prediction: Prediction,
):
    """
    Evaluate notification conditions for all users tracking this train.
    Called after every new prediction is written.
    """
    # Get all users tracking this train
    result = await db.execute(
        select(TrackedTrain).where(TrackedTrain.train_id == train_id)
    )
    tracked_trains = result.scalars().all()
    if not tracked_trains:
        return

    # Get the previous prediction for delta computation
    prev_result = await db.execute(
        select(Prediction)
        .where(Prediction.train_id == train_id)
        .where(Prediction.id != new_prediction.id)
        .order_by(desc(Prediction.created_at))
        .limit(1)
    )
    prev_prediction: Optional[Prediction] = prev_result.scalar_one_or_none()

    # Get the current position
    position = await db.get(TrainPosition, new_prediction.position_id)

    for tracked in tracked_trains:
        user_id = tracked.user_id
        prefs = await _get_prefs(db, user_id)
        threshold = prefs.min_delay_change_threshold_mins if prefs else settings.DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS

        # 1. Delay increase alert
        if prefs is None or prefs.delay_alerts:
            if prev_prediction:
                old_delay = float(prev_prediction.predicted_total_delay_mins or 0)
                new_delay = float(new_prediction.predicted_total_delay_mins or 0)
                delta = new_delay - old_delay
                if delta >= threshold:
                    if await _can_send(db, user_id, train_id, "delay_increase"):
                        train_name = await _get_train_name(db, train_id)
                        await _create_notification(
                            db, user_id, train_id,
                            type="delay_increase",
                            title=f"Delay Alert: {train_name}",
                            body=f"Train delay increased by {delta:.0f} mins. New total delay: {new_delay:.0f} mins.",
                            prediction_id=new_prediction.id,
                        )

        # 2. ETA change alert
        if prefs is None or prefs.eta_change_alerts:
            if prev_prediction and new_prediction.eta and prev_prediction.eta:
                old_eta = prev_prediction.eta
                new_eta = new_prediction.eta
                if old_eta.tzinfo is None:
                    old_eta = old_eta.replace(tzinfo=timezone.utc)
                if new_eta.tzinfo is None:
                    new_eta = new_eta.replace(tzinfo=timezone.utc)
                eta_delta_mins = abs((new_eta - old_eta).total_seconds() / 60)
                if eta_delta_mins >= threshold:
                    if await _can_send(db, user_id, train_id, "eta_change"):
                        train_name = await _get_train_name(db, train_id)
                        direction = "later" if new_eta > old_eta else "earlier"
                        await _create_notification(
                            db, user_id, train_id,
                            type="eta_change",
                            title=f"ETA Updated: {train_name}",
                            body=f"ETA is now {eta_delta_mins:.0f} mins {direction}. New ETA: {new_eta.strftime('%H:%M')}.",
                            prediction_id=new_prediction.id,
                        )

        # 3. Approaching destination alert
        if prefs is None or prefs.approaching_destination_alerts:
            if position and position.distance_remaining_km is not None:
                dist = float(position.distance_remaining_km)
                if 0 < dist <= settings.APPROACHING_DESTINATION_KM:
                    if await _can_send(db, user_id, train_id, "approaching_destination"):
                        train_name = await _get_train_name(db, train_id)
                        await _create_notification(
                            db, user_id, train_id,
                            type="approaching_destination",
                            title=f"Approaching Destination: {train_name}",
                            body=f"Train is {dist:.0f} km from your destination. ETA: {new_prediction.eta.strftime('%H:%M') if new_prediction.eta else 'N/A'}.",
                            prediction_id=new_prediction.id,
                        )

    await db.commit()


async def _can_send(
    db: AsyncSession, user_id: int, train_id: int, notif_type: str
) -> bool:
    """Check cooldown: has a notification of this type been sent in the last 15 minutes?"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=COOLDOWN_MINUTES)
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .where(Notification.train_id == train_id)
        .where(Notification.type == notif_type)
        .where(Notification.created_at >= cutoff)
        .limit(1)
    )
    return result.scalar_one_or_none() is None


async def _create_notification(
    db: AsyncSession,
    user_id: int,
    train_id: int,
    type: str,
    title: str,
    body: str,
    prediction_id: Optional[int] = None,
):
    notif = Notification(
        user_id=user_id,
        train_id=train_id,
        type=type,
        title=title,
        body=body,
        is_read=False,
        related_prediction_id=prediction_id,
    )
    db.add(notif)
    logger.info(f"Notification created: user={user_id} train={train_id} type={type}")


async def _get_prefs(db: AsyncSession, user_id: int) -> Optional[NotificationPreferences]:
    return await db.get(NotificationPreferences, user_id)


async def _get_train_name(db: AsyncSession, train_id: int) -> str:
    from app.models.train import Train
    train = await db.get(Train, train_id)
    return train.train_name if train else str(train_id)
