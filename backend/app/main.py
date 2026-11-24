from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.attendance import router as attendance_router
from app.api.auth import admin_router
from app.api.auth import router as auth_router
from app.api.cancellations import router as cancellations_router
from app.api.charges import router as charges_router
from app.api.events import router as events_router
from app.api.finance import guest_router as guest_finance_router
from app.api.finance import router as finance_router
from app.api.guests import router as guests_router
from app.api.health import router
from app.api.imports import router as import_router
from app.api.management import router as management_router
from app.api.payments import router as payments_router
from app.api.public import router as public_router
from app.api.registrations import admin_router as registration_admin_router
from app.api.registrations import public_router as registration_public_router
from app.api.reports import router as reports_router
from app.core.config import Settings
from app.core.database import build_engine, build_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configuration = settings or Settings()
        if configuration.auth_secret is None:
            raise RuntimeError("HASHTI_AUTH_SECRET is required")
        engine = build_engine(configuration.database_url.get_secret_value())
        application.state.settings = configuration
        application.state.engine = engine
        application.state.sessions = build_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Hashti API", version="0.1.0", lifespan=lifespan)
    application.include_router(router, prefix="/api")
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(management_router)
    application.include_router(events_router)
    application.include_router(guests_router)
    application.include_router(public_router)
    application.include_router(registration_public_router)
    application.include_router(registration_admin_router)
    application.include_router(finance_router)
    application.include_router(guest_finance_router)
    application.include_router(attendance_router)
    application.include_router(charges_router)
    application.include_router(cancellations_router)
    application.include_router(payments_router)
    application.include_router(reports_router)
    application.include_router(import_router)
    return application


app = create_app()
