from typing import Optional
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.utils.security import decode_access_token
from app.models.user import User


async def get_optional_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Returns the current user or None if unauthenticated. Use for routes with optional auth."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):]
    user_id = decode_access_token(token)
    if not user_id:
        return None
    user = await db.get(User, user_id)
    return user if user and user.is_active else None


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Returns the current user. Raises 401 if unauthenticated or token invalid."""
    user = await get_optional_current_user(authorization, db)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Authentication required."}},
        )
    return user
