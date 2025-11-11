from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalars().first()


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    user = User(
        email=data.email,
        full_name=data.full_name,
        hashed_password=get_password_hash(data.password),
        roles=data.roles,
        is_active=data.is_active,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(session, email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def update_user(session: AsyncSession, user: User, data: UserUpdate) -> User:
    payload = data.model_dump(exclude_unset=True)
    if password := payload.pop("password", None):
        user.hashed_password = get_password_hash(password)
    for field, value in payload.items():
        setattr(user, field, value)
    await session.flush()
    await session.refresh(user)
    return user
