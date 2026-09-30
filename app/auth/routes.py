import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.crypto import hash_password, verify_password
from app.auth.dependencies import get_current_user_id
from app.auth.rate_limit import (
    LOGIN_EMAIL_LIMIT,
    LOGIN_IP_LIMIT,
    LOGIN_WINDOW,
    SIGNUP_IP_LIMIT,
    SIGNUP_WINDOW,
    check_allowed,
    clear_failures,
    record_failure,
)
from app.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshResponse,
    SignupRequest,
    UserResponse,
)
from app.auth.tokens import create_access_token, create_refresh_token, hash_refresh_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuthSession, Membership, MembershipRole, Organization, User
from app.services.pipeline import create_default_pipeline

router = APIRouter(prefix="/auth", tags=["auth"])


def _csrf_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _session_cookie_name() -> str:
    return "__Host-fieldline_refresh" if get_settings().secure_cookies else "fieldline_refresh"


def _set_session_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.refresh_token_expire_days * 86400
    response.set_cookie(
        _session_cookie_name(),
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "fieldline_csrf",
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(_session_cookie_name(), path="/")
    response.delete_cookie("fieldline_csrf", path="/")


def _require_csrf(request: Request) -> str:
    cookie_value = request.cookies.get("fieldline_csrf")
    header_value = request.headers.get("X-CSRF-Token")
    if not cookie_value or not header_value or not secrets.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")
    return header_value


def _build_user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _create_session(db: Session, user_id: UUID) -> tuple[str, str]:
    settings = get_settings()
    refresh_token = create_refresh_token()
    csrf_token = secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        csrf_token_hash=_csrf_hash(csrf_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    return refresh_token, csrf_token


def _lookup_session(db: Session, refresh_token: str, *, lock: bool = False) -> AuthSession | None:
    statement = (
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == hash_refresh_token(refresh_token))
        .where(AuthSession.revoked_at.is_(None))
        .where(AuthSession.expires_at > datetime.now(UTC))
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _validate_session_csrf(csrf_token: str, session: AuthSession) -> None:
    if not secrets.compare_digest(_csrf_hash(csrf_token), session.csrf_token_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    client_ip = request.client.host if request.client else "unknown"
    check_allowed(db, "signup-ip", client_ip, SIGNUP_IP_LIMIT, SIGNUP_WINDOW)

    email = str(payload.email).lower()
    slug = "-".join(payload.organization_name.lower().split())[:80].strip("-") or "organization"
    if not slug[0].isalnum():
        slug = "org-" + slug

    existing = db.scalar(select(User).where(func.lower(User.email) == email).limit(1))
    if existing:
        record_failure(db, "signup-ip", client_ip, SIGNUP_IP_LIMIT, SIGNUP_WINDOW)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create account")

    organization = Organization(name=payload.organization_name, slug=slug)
    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    membership = Membership(role=MembershipRole.OWNER, organization=organization, user=user)
    db.add_all([organization, user, membership])
    try:
        db.flush()
        create_default_pipeline(db, organization.id)
        refresh_token, csrf_token = _create_session(db, user.id)
        db.commit()
        user = db.scalar(
            select(User).options(selectinload(User.memberships)).where(User.id == user.id)
        ) or user
    except IntegrityError as exc:
        db.rollback()
        record_failure(db, "signup-ip", client_ip, SIGNUP_IP_LIMIT, SIGNUP_WINDOW)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create account",
        ) from exc

    clear_failures(db, "signup-ip", client_ip)
    _set_session_cookies(response, refresh_token, csrf_token)
    return AuthResponse(access_token=create_access_token(user.id), user=_build_user_response(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    login_key = f"{email}|{client_ip}"
    check_allowed(db, "login-email", login_key, LOGIN_EMAIL_LIMIT, LOGIN_WINDOW)
    check_allowed(db, "login-ip", client_ip, LOGIN_IP_LIMIT, LOGIN_WINDOW)

    user = db.scalar(
        select(User)
        .options(selectinload(User.memberships))
        .where(func.lower(User.email) == email)
        .limit(1)
    )
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        record_failure(db, "login-email", login_key, LOGIN_EMAIL_LIMIT, LOGIN_WINDOW)
        record_failure(db, "login-ip", client_ip, LOGIN_IP_LIMIT, LOGIN_WINDOW)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    clear_failures(db, "login-email", login_key)
    refresh_token, csrf_token = _create_session(db, user.id)
    db.commit()
    _set_session_cookies(response, refresh_token, csrf_token)
    return AuthResponse(access_token=create_access_token(user.id), user=_build_user_response(user))


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> RefreshResponse:
    csrf_token = _require_csrf(request)
    refresh_token = request.cookies.get(_session_cookie_name())
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    now = datetime.now(UTC)
    session = _lookup_session(db, refresh_token, lock=True)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    _validate_session_csrf(csrf_token, session)

    user = db.scalar(
        select(User).options(selectinload(User.memberships)).where(User.id == session.user_id)
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    session.revoked_at = now
    session.last_used_at = now
    refresh_token_new, csrf_token_new = _create_session(db, user.id)
    db.commit()
    _set_session_cookies(response, refresh_token_new, csrf_token_new)
    return RefreshResponse(
        access_token=create_access_token(user.id),
        user=_build_user_response(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    csrf_token = _require_csrf(request)
    refresh_token = request.cookies.get(_session_cookie_name())
    if refresh_token:
        session = _lookup_session(db, refresh_token, lock=True)
        if session:
            _validate_session_csrf(csrf_token, session)
            session.revoked_at = datetime.now(UTC)
            db.commit()
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def me(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> UserResponse:
    user = db.scalar(select(User).options(selectinload(User.memberships)).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _build_user_response(user)
