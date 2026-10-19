from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user_id
from app.db.session import get_db
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

router = APIRouter(
    prefix="/organizations/{organization_id}",
    tags=["engagement"],
)


@router.post(
    "/activities",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_activity(
    organization_id: UUID,
    payload: ActivityCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_activity(db, organization_id, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/activities", response_model=list[ActivityResponse])
async def get_activities(
    organization_id: UUID,
    limit: int = Query(default=100, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await list_activities(db, organization_id, limit)


@router.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_task(
    organization_id: UUID,
    payload: TaskCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_task(db, organization_id, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(
    organization_id: UUID,
    limit: int = Query(default=100, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await list_tasks(db, organization_id, limit)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def patch_task(
    organization_id: UUID,
    task_id: UUID,
    payload: TaskUpdate,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    from app.models import Task

    task = await db.get(Task, task_id)
    if task is None or task.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        return await update_task(db, task, organization_id, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
