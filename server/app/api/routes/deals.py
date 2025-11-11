from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user
from app.api.dependencies.database import get_db
from app.models.deal import DealStage
from app.models.user import User
from app.schemas.approval import ApprovalCreate, ApprovalRead, ApprovalUpdate
from app.schemas.deal import DealCollection, DealCreate, DealRead, DealSummary, DealUpdate
from app.services.deal_service import DealFilters, add_approval, create_deal, get_deal, list_deals, update_deal, upsert_approval


router = APIRouter(prefix="/deals", tags=["deals"])


Pagination = Annotated[int, Query(ge=1)]


@router.get("", response_model=DealCollection)
async def list_deals_endpoint(
    page: Pagination = 1,
    page_size: Pagination = Query(default=20, le=100),
    search: str | None = Query(default=None, min_length=2),
    stage: DealStage | None = None,
    owner_id: str | None = None,
    min_probability: int | None = Query(default=None, ge=0, le=100),
    max_probability: int | None = Query(default=None, ge=0, le=100),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001 - scope checks hook point
) -> DealCollection:
    filters = DealFilters(
        search=search,
        stage=stage,
        owner_id=owner_id,
        min_probability=min_probability,
        max_probability=max_probability,
    )
    items, total = await list_deals(session, filters=filters, page=page, page_size=page_size)
    return DealCollection(
        items=[DealSummary.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DealRead, status_code=status.HTTP_201_CREATED)
async def create_deal_endpoint(
    payload: DealCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DealRead:
    if payload.owner_id is None:
        payload.owner_id = current_user.id
    deal = await create_deal(session, payload)
    await session.commit()
    refreshed = await get_deal(session, deal.id)
    if refreshed is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Deal not found post-creation")
    return DealRead.model_validate(refreshed)


@router.get("/{deal_id}", response_model=DealRead)
async def get_deal_endpoint(
    deal_id: str,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> DealRead:
    deal = await get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return DealRead.model_validate(deal)


@router.patch("/{deal_id}", response_model=DealRead)
async def update_deal_endpoint(
    deal_id: str,
    payload: DealUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> DealRead:
    deal = await get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    updated = await update_deal(session, deal, payload)
    await session.commit()
    await session.refresh(updated)
    return DealRead.model_validate(updated)


@router.post("/{deal_id}/approvals", response_model=ApprovalRead, status_code=status.HTTP_201_CREATED)
async def add_deal_approval(
    deal_id: str,
    payload: ApprovalCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> ApprovalRead:
    deal = await get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    approval = await add_approval(session, deal, payload)
    await session.commit()
    await session.refresh(approval)
    return ApprovalRead.model_validate(approval)


@router.patch("/{deal_id}/approvals/{approval_id}", response_model=ApprovalRead)
async def update_deal_approval(
    deal_id: str,
    approval_id: str,
    payload: ApprovalUpdate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> ApprovalRead:
    deal = await get_deal(session, deal_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    approval = next((item for item in deal.approvals if item.id == approval_id), None)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    updated = await upsert_approval(session, approval, payload)
    await session.commit()
    await session.refresh(updated)
    return ApprovalRead.model_validate(updated)
