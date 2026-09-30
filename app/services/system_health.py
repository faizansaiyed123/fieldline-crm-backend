from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AutomationRun
from app.schemas.standout import SystemHealthCheck, SystemHealthResponse

EXPECTED_MIGRATION = "0012_standout"


def get_system_health(db: Session) -> SystemHealthResponse:
    now = datetime.now(UTC)
    checks: dict[str, SystemHealthCheck] = {}
    overall = "ok"

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = SystemHealthCheck(status="ok", detail="PostgreSQL connection succeeded")
    except SQLAlchemyError:
        checks["database"] = SystemHealthCheck(status="error", detail="PostgreSQL connection failed")
        return SystemHealthResponse(generated_at=now, status="error", checks=checks)

    version = db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    if version == EXPECTED_MIGRATION:
        checks["migrations"] = SystemHealthCheck(status="ok", detail=f"Database is at {version}")
    else:
        checks["migrations"] = SystemHealthCheck(
            status="warning",
            detail=f"Database reports migration {version or 'none'}; expected {EXPECTED_MIGRATION}",
        )
        overall = "warning"

    extension = db.scalar(
        text("SELECT extname FROM pg_extension WHERE extname = 'pg_trgm' LIMIT 1")
    )
    if extension == "pg_trgm":
        checks["pg_trgm"] = SystemHealthCheck(status="ok", detail="Fuzzy matching extension is installed")
    else:
        checks["pg_trgm"] = SystemHealthCheck(
            status="error",
            detail="pg_trgm extension is missing; data-quality duplicate detection is unavailable",
        )
        overall = "error"

    since = now - timedelta(hours=24)
    failed_automations = db.scalar(
        select(func.count())
        .select_from(AutomationRun)
        .where(AutomationRun.created_at >= since)
        .where(AutomationRun.status != "completed")
    ) or 0
    if failed_automations:
        checks["automation"] = SystemHealthCheck(
            status="warning",
            detail=f"{int(failed_automations)} automation run(s) are not completed in the last 24 hours",
        )
        if overall == "ok":
            overall = "warning"
    else:
        checks["automation"] = SystemHealthCheck(status="ok", detail="No incomplete automation runs in the last 24 hours")

    checks["application"] = SystemHealthCheck(
        status="ok",
        detail="Fieldline API process is responding",
    )
    return SystemHealthResponse(generated_at=now, status=overall, checks=checks)
