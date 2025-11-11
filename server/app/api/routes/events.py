from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.models.user import User
from app.services.outbox_service import dispatch_pending_events


router = APIRouter(prefix="/events", tags=["events"])


@router.post("/dispatch")
async def dispatch_events_endpoint(
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 - scope enforcement via auth layer
) -> dict[str, int]:
    dispatched = await dispatch_pending_events(session)
    await session.commit()
    return {"dispatched": dispatched}
