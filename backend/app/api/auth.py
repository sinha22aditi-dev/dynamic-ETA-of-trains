from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, NotificationPreferences
from app.schemas.requests import UserRegisterRequest, UserLoginRequest
from app.schemas.responses import UserResponse, TokenResponse
from app.utils.security import hash_password, verify_password, create_access_token
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=dict, status_code=201)
async def register(body: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "EMAIL_TAKEN", "message": "Email already registered."}}
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    # Create default notification preferences
    prefs = NotificationPreferences(
        user_id=user.id,
        min_delay_change_threshold_mins=settings.DEFAULT_MIN_DELAY_CHANGE_THRESHOLD_MINS,
    )
    db.add(prefs)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return {
        "user": UserResponse.model_validate(user).model_dump(),
        "token": {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    }


@router.post("/login", response_model=dict)
async def login(body: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail={"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}}
        )
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "ACCOUNT_DISABLED", "message": "Account is disabled."}}
        )

    token = create_access_token(user.id)
    return {
        "user": UserResponse.model_validate(user).model_dump(),
        "token": {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    }


@router.get("/me", response_model=UserResponse)
async def me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return UserResponse.model_validate(current_user)
