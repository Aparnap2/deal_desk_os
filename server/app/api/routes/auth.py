from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.database import get_db
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import TokenResponse, get_token_expiry_seconds
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import authenticate_user, create_user, get_user_by_email


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect credentials")
    settings = get_settings()
    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        expires_in=get_token_expiry_seconds(settings.access_token_expire_minutes),
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, session: AsyncSession = Depends(get_db)) -> UserRead:
    existing = await get_user_by_email(session, payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
    user = await create_user(session, payload)
    await session.commit()
    return UserRead.model_validate(user)
