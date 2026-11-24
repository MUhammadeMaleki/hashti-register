import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/health", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("")
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": "hashti-api"}


@router.get("/ready")
def readiness(request: Request) -> JSONResponse:
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # No connection strings, SQL parameters, or exception text in public output/logs.
        logger.warning("database_readiness_failed")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ok", "database": "postgresql"})
