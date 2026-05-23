"""Pipeline (Kanban) + notes, scopeados por usuario."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import db
from deps import get_current_user
from schemas import NoteIn, PipelineUpdate

router = APIRouter(tags=["pipeline"])


@router.get("/pipeline")
def get_pipeline_list(status: Optional[str] = Query(default=None), user=Depends(get_current_user)):
    rows = db.list_pipeline(user_id=user["user_id"], status=status)
    result = []
    for row in rows:
        r = dict(row)
        if r.get("updated_at"):
            r["updated_at"] = r["updated_at"].isoformat()
        result.append(r)
    return {"items": result, "count": len(result), "statuses": db.PIPELINE_STATUSES}


@router.get("/pipeline/statuses", dependencies=[Depends(get_current_user)])
def get_statuses():
    return {"statuses": db.PIPELINE_STATUSES}


@router.put("/opportunities/{opportunity_id}/pipeline")
def update_pipeline(opportunity_id: int, payload: PipelineUpdate, user=Depends(get_current_user)):
    if payload.status not in db.PIPELINE_STATUSES:
        raise HTTPException(status_code=400, detail=f"Estado inválido. Opciones: {db.PIPELINE_STATUSES}")
    row = db.upsert_pipeline(opportunity_id, user["user_id"], payload.status, payload.assignee)
    if row.get("updated_at"):
        row["updated_at"] = row["updated_at"].isoformat()
    if row.get("created_at"):
        row["created_at"] = row["created_at"].isoformat()
    return row


@router.get("/opportunities/{opportunity_id}/pipeline")
def get_opp_pipeline(opportunity_id: int, user=Depends(get_current_user)):
    row = db.get_pipeline(opportunity_id, user["user_id"])
    if not row:
        return {"opportunity_id": opportunity_id, "status": None, "assignee": None}
    if row.get("updated_at"):
        row["updated_at"] = row["updated_at"].isoformat()
    if row.get("created_at"):
        row["created_at"] = row["created_at"].isoformat()
    return row


@router.post("/opportunities/{opportunity_id}/notes")
def add_note(opportunity_id: int, payload: NoteIn, user=Depends(get_current_user)):
    row = db.add_pipeline_note(opportunity_id, user["user_id"], payload.note, payload.author)
    if row.get("created_at"):
        row["created_at"] = row["created_at"].isoformat()
    return row


@router.get("/opportunities/{opportunity_id}/notes")
def get_notes(opportunity_id: int, user=Depends(get_current_user)):
    rows = db.get_pipeline_notes(opportunity_id, user["user_id"])
    result = []
    for row in rows:
        r = dict(row)
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        result.append(r)
    return {"items": result}
