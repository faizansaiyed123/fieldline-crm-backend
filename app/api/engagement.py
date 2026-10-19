from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.authorization import require_membership
from app.db.session import get_db
from app.models import Membership, Task
from app.schemas.engagement import (
    ActivityCreate,
    ActivityResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.services.engagement import (
    create_activity,
    create_task,
    list_activities,
    list_tasks,
    update_task,
)

router = APIRouter(prefix="/organizations/{organization_id}/engagement", tags=["engagement"])


@router.post("/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
def post_activity(
    organization_id: UUID,
    payload: ActivityCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> ActivityResponse:
    try:
        activity = create_activity(db, organization_id, membership.user_id, payload)
        response = ActivityResponse.model_validate(activity)
        response.created_at = activity.occurred_at
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/activities", response_model=list[ActivityResponse])
def get_activities(
    organization_id: UUID,
    limit: int = Query(default=100, ge=1, le=100),
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> list[ActivityResponse]:
    responses = [ActivityResponse.model_validate(item) for item in list_activities(db, organization_id, limit)]
    for response in responses:
        response.created_at = response.occurred_at
    return responses


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def post_task(
    organization_id: UUID,
    payload: TaskCreate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> TaskResponse:
    try:
        task = create_task(db, organization_id, membership.user_id, payload)
        response = TaskResponse.model_validate(task)
        response.completed = task.completed_at is not None
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/tasks", response_model=list[TaskResponse])
def get_tasks(
    organization_id: UUID,
    limit: int = Query(default=100, ge=1, le=100),
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> list[TaskResponse]:
    tasks = list_tasks(db, organization_id, limit)
    responses = [TaskResponse.model_validate(item) for item in tasks]
    for response, task in zip(responses, tasks, strict=True):
        response.completed = task.completed_at is not None
    return responses


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def patch_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    membership: Membership = Depends(require_membership),
    db: Session = Depends(get_db),
) -> TaskResponse:
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .where(Task.organization_id == organization_id)
        .limit(1)
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    try:
        updated = update_task(db, task, organization_id, membership.user_id, payload)
        response = TaskResponse.model_validate(updated)
        response.completed = updated.completed_at is not None
        return response
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
