from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class UserRole(str, Enum):
    SALES = "sales"
    LEGAL = "legal"
    FINANCE = "finance"
    EXECUTIVE = "executive"
    ADMIN = "admin"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[Identifier]
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    owned_deals: Mapped[list["Deal"]] = relationship(back_populates="owner", cascade="all,delete")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="approver", cascade="all,delete")
