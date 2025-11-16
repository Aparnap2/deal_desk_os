from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, auth, deals, events, invoices, payments, health, users, sla_dashboard, monitoring, policies
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import lifespan
from app.services.guardrail_service import initialize_policy_service
from app.db.session import SessionLocal


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
    application.include_router(invoices.router)
    application.include_router(events.router)
    application.include_router(analytics.router)
    application.include_router(sla_dashboard.router)
    application.include_router(monitoring.router)
    application.include_router(policies.router)

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

        # Initialize policy service for guardrail integration
        db = SessionLocal()
        try:
            initialize_policy_service(db)
            logger.info("policy_service.initialized")
        except Exception as e:
            logger.error("policy_service.initialization_failed", error=str(e))
        finally:
            db.close()

    @application.on_event("shutdown")
    async def shutdown_event() -> None:  # pragma: no cover - side effect
        logger.info("application.shutdown")

    return application


app = create_application()
