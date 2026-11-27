"""Inbound webhooks. WordPress posts form submissions here (signed with HMAC)."""
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..auth import verify_webhook
from ..db import SessionLocal, get_db
from ..models import Application
from ..services.intake import ingest_application
from ..services.processing import process_application

router = APIRouter(prefix="/api/webhooks")


class WPSubmission(BaseModel):
    entry_id: str               # unique per submission (idempotency key)
    form_id: str = ""
    email: str
    full_name: str = ""
    phone: str = ""
    position: str = ""
    fields: dict = {}


def _process_async(app_id: int) -> None:
    db = SessionLocal()
    try:
        app = db.get(Application, app_id)
        if app:
            process_application(db, app)
            db.commit()
    finally:
        db.close()


@router.post("/wordpress", status_code=202)
def wordpress(background: BackgroundTasks, raw: bytes = Depends(verify_webhook), db: Session = Depends(get_db)):
    try:
        data = WPSubmission(**json.loads(raw))
        app, created = ingest_application(db, source="wordpress", external_id=f"{data.form_id}:{data.entry_id}",
                                          email=data.email, full_name=data.full_name, phone=data.phone,
                                          position=data.position, fields=data.fields)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)[:300])
    db.commit()
    if created:
        background.add_task(_process_async, app.id)  # AI work happens after the 202 is returned
    return {"application_id": app.id, "applicant_id": app.applicant_id, "created": created,
            "duplicate": app.is_duplicate}
