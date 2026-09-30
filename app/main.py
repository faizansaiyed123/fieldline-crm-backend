from fastapi import FastAPI, Request

from app.api.attention import router as attention_router
from app.api.automation import router as automation_router
from app.api.companies import router as companies_router
from app.api.contacts import router as contacts_router
from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.api.opportunities import router as opportunities_router
from app.api.organizations import router as organizations_router
from app.api.pipeline import router as pipeline_router
from app.api.relationship_health import router as relationship_health_router
from app.api.saved_views import router as saved_views_router
from app.api.standout import router as standout_router
from app.api.timeline import router as timeline_router
from app.auth.routes import router as auth_router
from app.core.config import get_settings
from app.core.http import internal_error_handler, request_context

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url=f"{settings.api_prefix}/docs",
    redoc_url=f"{settings.api_prefix}/redoc",
    openapi_url=f"{settings.api_prefix}/openapi.json",
)

app.middleware("http")(request_context)
app.add_exception_handler(Exception, internal_error_handler)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(organizations_router, prefix=settings.api_prefix)
app.include_router(companies_router, prefix=settings.api_prefix)
app.include_router(contacts_router, prefix=settings.api_prefix)
app.include_router(pipeline_router, prefix=settings.api_prefix)
app.include_router(opportunities_router, prefix=settings.api_prefix)
app.include_router(timeline_router, prefix=settings.api_prefix)
app.include_router(attention_router, prefix=settings.api_prefix)
app.include_router(automation_router, prefix=settings.api_prefix)
app.include_router(imports_router, prefix=settings.api_prefix)
app.include_router(saved_views_router, prefix=settings.api_prefix)
app.include_router(standout_router, prefix=settings.api_prefix)
app.include_router(relationship_health_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
def root(request: Request) -> dict[str, str]:
    return {"service": "fieldline-api", "status": "ok"}
