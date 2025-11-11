from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, auth, deals, events, payments, health, users
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import lifespan


configure_logging()
logger = get_logger(__name__)


def create_application() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(users.router)
    application.include_router(deals.router)
    application.include_router(payments.router)
    application.include_router(events.router)
    application.include_router(analytics.router)

    if settings.allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.allowed_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @application.on_event("startup")
    async def startup_event() -> None:  # pragma: no cover - side effect
        logger.info("application.startup", environment=settings.environment)

    @application.on_event("shutdown")
    async def shutdown_event() -> None:  # pragma: no cover - side effect
        logger.info("application.shutdown")

    return application


app = create_application()
