from typing import List

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel, Timestamped


class UserBase(ORMModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    roles: List[str] = Field(default_factory=list)
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=12, max_length=128)


class UserUpdate(ORMModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    roles: List[str] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


class UserRead(UserBase, Timestamped):
    id: str
