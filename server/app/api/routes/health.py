from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Health check")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
