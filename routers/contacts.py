"""CRUD de contactos."""
import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

import db
from deps import get_current_user, require_feature
from plans import features_for
from schemas import ContactIn, ContactUpdate
from ai_email import generate_draft

router = APIRouter(tags=["contacts"], dependencies=[Depends(get_current_user)])

@router.post("/contacts/{contact_id}/generate-email")
def generate_email_draft(contact_id: int, user=Depends(get_current_user)):
    contact = db.get_contact(contact_id, user["user_id"])
    if not contact:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")

    company = contact.get("company", "")
    recent_projects = []
    if company:
        recent_projects = db.get_opportunities_by_company(company)[:3]

    draft = generate_draft(
        contact_name=contact.get("name", ""),
        contact_role=contact.get("role", ""),
        company=company,
        recent_projects=recent_projects
    )
    return draft


@router.get("/contacts")
def get_contacts(
    q: Optional[str] = Query(default=None),
    company: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    user=Depends(get_current_user),
):
    if company:
        rows = db.get_contacts_by_company(company, user["user_id"])
    else:
        rows = db.list_contacts(user["user_id"], q=q, limit=limit)
    result = []
    for row in rows:
        r = dict(row)
        for f in ["created_at", "updated_at"]:
            if r.get(f):
                r[f] = r[f].isoformat()
        result.append(r)
    return {"items": result, "count": len(result)}


@router.post("/contacts")
def add_contact(payload: ContactIn, user=Depends(get_current_user)):
    # Enforce max_contacts del plan
    plan = db.get_user_plan(user["user_id"])
    limit = features_for(plan.get("plan", "free")).get("max_contacts", 50)
    current = db.count_user_contacts(user["user_id"])
    if current >= limit:
        raise HTTPException(
            status_code=402,
            detail=f"Llegaste al tope de contactos de tu plan ({limit}). Actualizá tu plan en /pricing.html.",
        )
    row = db.create_contact(payload.model_dump(), user["user_id"])
    for f in ["created_at", "updated_at"]:
        if row.get(f):
            row[f] = row[f].isoformat()
    return row


@router.put("/contacts/{contact_id}")
def edit_contact(contact_id: int, payload: ContactUpdate, user=Depends(get_current_user)):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    row = db.update_contact(contact_id, data, user["user_id"])
    if not row:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    for f in ["created_at", "updated_at"]:
        if row.get(f):
            row[f] = row[f].isoformat()
    return row


@router.delete("/contacts/{contact_id}")
def remove_contact(contact_id: int, user=Depends(get_current_user)):
    ok = db.delete_contact(contact_id, user["user_id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return {"ok": True}


@router.post("/contacts/import")
def import_contacts(payload: List[ContactIn], user=Depends(get_current_user)):
    # Enforce max_contacts del plan considerando lo que ya tiene + lo que importa.
    plan = db.get_user_plan(user["user_id"])
    limit = features_for(plan.get("plan", "free")).get("max_contacts", 50)
    current = db.count_user_contacts(user["user_id"])
    if current + len(payload) > limit:
        raise HTTPException(
            status_code=402,
            detail=f"La importación supera el tope de tu plan ({limit} contactos). "
                   f"Tenés {current}; intentás agregar {len(payload)}. Actualizá tu plan en /pricing.html.",
        )
    contacts = [c.model_dump() for c in payload]
    inserted, errors = db.bulk_import_contacts(contacts, user["user_id"])
    return {"ok": True, "inserted": inserted, "errors": errors}


@router.get("/contacts/export", dependencies=[Depends(require_feature("exports"))])
def export_contacts(user=Depends(get_current_user)):
    rows = db.list_contacts(user["user_id"], limit=10000)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "name", "company", "role", "email", "phone", "linkedin_url", "notes", "created_at"],
    )
    writer.writeheader()
    for row in rows:
        r = dict(row)
        if r.get("created_at"):
            r["created_at"] = r["created_at"].isoformat()
        writer.writerow({k: r.get(k, "") for k in writer.fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contactos_stratmap.csv"},
    )
