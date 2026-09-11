from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.notification import Notification
from app.models.user import NotificationPreferences
from app.schemas.requests import NotificationPreferencesRequest
from app.config import settings

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=dict)
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read == False)
    stmt = stmt.order_by(desc(Notification.created_at)).limit(limit).offset(offset)

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return {
        "total": len(notifications),
        "items": [
            {
                "id": n.id,
                "train_id": n.train_id,
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ]
    }


@router.patch("/{notification_id}/read", response_model=dict)
async def mark_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    notif = await db.get(Notification, notification_id)
    if not notif or notif.user_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "NOT_FOUND", "message": "Notification not found."}}
        )
    notif.is_read = True
    await db.commit()
    return {"id": notif.id, "is_read": True}


@router.post("/read-all", response_model=dict)
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id)
        .where(Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"message": "All notifications marked as read."}


@router.get("/preferences", response_model=dict)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await db.get(NotificationPreferences, current_user.id)
    if not prefs:
        return {
            "user_id": current_user.id,
            "delay_alerts": True,
            "eta_change_alerts": True,
            "approaching_destination_alerts": True,
            "min_delay_change_threshold_mins": settings.DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS,
        }
    return {
        "user_id": prefs.user_id,
        "delay_alerts": prefs.delay_alerts,
        "eta_change_alerts": prefs.eta_change_alerts,
        "approaching_destination_alerts": prefs.approaching_destination_alerts,
        "min_delay_change_threshold_mins": prefs.min_delay_change_threshold_mins,
    }


@router.patch("/preferences", response_model=dict)
async def update_preferences(
    body: NotificationPreferencesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    prefs = await db.get(NotificationPreferences, current_user.id)
    if not prefs:
        prefs = NotificationPreferences(
            user_id=current_user.id,
            min_delay_change_threshold_mins=settings.DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS,
        )
        db.add(prefs)

    if body.delay_alerts is not None:
        prefs.delay_alerts = body.delay_alerts
    if body.eta_change_alerts is not None:
        prefs.eta_change_alerts = body.eta_change_alerts
    if body.approaching_destination_alerts is not None:
        prefs.approaching_destination_alerts = body.approaching_destination_alerts
    if body.min_delay_change_threshold_mins is not None:
        prefs.min_delay_change_threshold_mins = body.min_delay_change_threshold_mins

    await db.commit()
    return {"message": "Preferences updated.", "user_id": current_user.id}
