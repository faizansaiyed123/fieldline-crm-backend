from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Company, Membership
from app.schemas.company import CompanyCreate, CompanyListResponse, CompanyResponse, CompanyUpdate
from app.services.company import archive_company, create_company, get_company, update_company

router = APIRouter(prefix="/organizations/{organization_id}/companies", tags=["companies"])


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create(
    organization_id: UUID,
    payload: CompanyCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    try:
        company = create_company(
            db,
            organization_id=organization_id,
            actor_user_id=membership.user_id,
            name=payload.name,
            website=str(payload.website) if payload.website else None,
            phone=payload.phone,
        )
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        detail = str(exc) if isinstance(exc, ValueError) else "A company with this name already exists"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
    return CompanyResponse.model_validate(company)


@router.get("", response_model=CompanyListResponse)
def list_companies(
    organization_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    owner_user_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> CompanyListResponse:
    statement = (
        select(Company)
        .where(Company.organization_id == organization_id)
        .where(Company.deleted_at.is_(None))
    )
    if q:
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                Company.name.ilike(term),
                Company.website.ilike(term),
                Company.phone.ilike(term),
            )
        )
    if owner_user_id:
        statement = statement.where(Company.owner_user_id == owner_user_id)

    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    items = db.scalars(
        statement.order_by(Company.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
def get(
    organization_id: UUID,
    company_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    company = get_company(db, organization_id=organization_id, company_id=company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
def update(
    organization_id: UUID,
    company_id: UUID,
    payload: CompanyUpdate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> CompanyResponse:
    company = get_company(db, organization_id=organization_id, company_id=company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return CompanyResponse.model_validate(company)
    try:
        update_company(db, company=company, actor_user_id=membership.user_id, changes=changes)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        detail = str(exc) if isinstance(exc, ValueError) else "A company with this name already exists"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive(
    organization_id: UUID,
    company_id: UUID,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> Response:
    company = get_company(db, organization_id=organization_id, company_id=company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    archive_company(db, company=company, actor_user_id=membership.user_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
