from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.authorization import require_roles
from app.db.session import get_db
from app.models import Membership, MembershipRole
from app.schemas.imports import (
    ImportCommitRequest,
    ImportCommitResponse,
    ImportJobResponse,
    ImportPreviewResponse,
)
from app.services.imports import (
    _preview_response,
    commit_contact_import,
    get_import_job,
    preview_contact_import,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/imports",
    tags=["imports"],
)


@router.post(
    "/contacts/preview",
    response_model=ImportPreviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def preview_contacts(
    organization_id: UUID,
    file: UploadFile = File(...),
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> ImportPreviewResponse:
    try:
        content = await file.read()
        job, rows = preview_contact_import(
            db,
            organization_id=organization_id,
            actor_user_id=membership.user_id,
            filename=file.filename or "contacts.csv",
            content_type=file.content_type,
            content=content,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Import could not be staged") from exc

    return ImportPreviewResponse.model_validate(_preview_response(job, rows))


@router.get("/{job_id}", response_model=ImportJobResponse)
def get_job(
    organization_id: UUID,
    job_id: UUID,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    job = get_import_job(db, organization_id=organization_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return ImportJobResponse.model_validate(job)


@router.post("/{job_id}/commit", response_model=ImportCommitResponse)
def commit(
    organization_id: UUID,
    job_id: UUID,
    payload: ImportCommitRequest,
    membership: Membership = Depends(
        require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)
    ),
    db: Session = Depends(get_db),
) -> ImportCommitResponse:
    job = get_import_job(db, organization_id=organization_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")

    try:
        would_create, committed = commit_contact_import(
            db,
            job=job,
            actor_user_id=membership.user_id,
            dry_run=payload.dry_run,
        )
        if payload.dry_run:
            db.rollback()
        else:
            db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Import failed and all contact changes were rolled back",
        ) from exc

    return ImportCommitResponse(
        job_id=job.id,
        status="dry_run" if payload.dry_run else job.status,
        dry_run=payload.dry_run,
        total_rows=job.total_rows,
        valid_rows=job.valid_rows,
        invalid_rows=job.invalid_rows,
        would_create=would_create,
        committed_rows=committed,
    )
