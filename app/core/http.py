import logging
import re
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger("fieldline.http")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


async def request_context(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID")
    request_id = incoming if incoming and _REQUEST_ID_RE.fullmatch(incoming) else uuid4().hex
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled request exception", extra={"request_id": request_id})
        raise

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

    if request.url.path.startswith(f"{get_settings().api_prefix}/auth/"):
        response.headers["Cache-Control"] = "no-store"

    if get_settings().environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "unhandled application exception",
        exc_info=exc,
        extra={"request_id": request_id},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )
