from datetime import datetime
from typing import Annotated

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)]


class TimestampMixin:
    created_at: Mapped[Timestamp]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
