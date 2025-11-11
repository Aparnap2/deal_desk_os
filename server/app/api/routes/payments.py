from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.api.dependencies.redis import get_redis_client
from app.models.deal import GuardrailStatus
from app.models.user import User
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services.deal_service import get_deal
from app.services.payment_service import process_payment


router = APIRouter(prefix="/deals/{deal_id}/payments", tags=["payments"])


@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def create_payment_endpoint(
    deal_id: str,
    payload: PaymentCreate,
    session: AsyncSession = Depends(get_db),
    redis_client: Redis | None = Depends(get_redis_client),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 - auditing handled elsewhere
) -> PaymentRead:
    deal = await get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    if deal.guardrail_status is GuardrailStatus.VIOLATED:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Guardrail violation blocks payment")
    payment = await process_payment(session, deal=deal, payload=payload, redis_client=redis_client)
    await session.commit()
    await session.refresh(payment)
    return PaymentRead.model_validate(payment)
