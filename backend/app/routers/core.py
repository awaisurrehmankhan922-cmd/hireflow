"""Authenticated admin API: auth, applicants, conversations, automation, settings, knowledge base."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from ..auth import COOKIE, create_token, current_admin, hash_password, verify_password
from ..config import get_settings
from ..db import get_db
from ..llm import get_provider
from ..models import (AdminUser, Applicant, Application, AuditLog, FollowUpRule, KnowledgeArticle, Message, utcnow)
from ..serializers import applicant_out, message_out
from ..services import ai_engine
from ..services.audit import audit
from ..services.mailer import send_message
from ..services.settings_store import DEFAULTS, all_settings, set_setting

router = APIRouter(prefix="/api")
Admin = Depends(current_admin)


# ---------- auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter_by(email=body.email.lower(), is_active=True).first()
    if not user or not verify_password(body.password, user.password_hash):
        audit(db, body.email, "login_failed")
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.email)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=60 * 60 * 12)
    audit(db, user.email, "login")
    return {"access_token": token, "token_type": "bearer", "email": user.email}


@router.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@router.get("/auth/me")
def me(user: AdminUser = Admin):
    return {"email": user.email, "full_name": user.full_name}


@router.get("/auth/verify")
def verify_for_proxy(response: Response, user: AdminUser = Admin):
    """Used by nginx auth_request to gate Open WebUI behind the dashboard login."""
    response.headers["X-User-Email"] = user.email
    response.headers["X-User-Name"] = user.full_name or user.email
    return {"ok": True}


class AdminIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""


@router.get("/admins")
def list_admins(db: Session = Depends(get_db), _=Admin):
    return [{"id": u.id, "email": u.email, "full_name": u.full_name, "is_active": u.is_active}
            for u in db.query(AdminUser).order_by(AdminUser.id)]


@router.post("/admins", status_code=201)
def create_admin(body: AdminIn, db: Session = Depends(get_db), user=Admin):
    if len(body.password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters")
    if db.query(AdminUser).filter_by(email=body.email.lower()).first():
        raise HTTPException(409, "Admin exists")
    u = AdminUser(email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(u)
    db.commit()
    audit(db, user.email, "admin_created", "admin", u.id, email=u.email)
    return {"id": u.id}


@router.delete("/admins/{admin_id}")
def deactivate_admin(admin_id: int, db: Session = Depends(get_db), user=Admin):
    u = db.get(AdminUser, admin_id) or _404()
    if u.email == user.email:
        raise HTTPException(400, "Cannot deactivate yourself")
    u.is_active = False
    audit(db, user.email, "admin_deactivated", "admin", u.id)
    return {"ok": True}


# ---------- applicants ----------
@router.get("/applicants")
def list_applicants(q: str = "", status: str = "", classification: str = "", attention: bool = False,
                    db: Session = Depends(get_db), _=Admin):
    query = db.query(Applicant)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(Applicant.email).like(like), func.lower(Applicant.full_name).like(like)))
    if status:
        query = query.filter(Applicant.status == status)
    rows = [applicant_out(a) for a in query.order_by(Applicant.id.desc()).limit(500)]
    if classification:
        rows = [r for r in rows if r["classification"] == classification]
    if attention:
        rows = [r for r in rows if r["needs_attention"]]
    return rows


@router.get("/applicants/{applicant_id}")
def get_applicant(applicant_id: int, db: Session = Depends(get_db), _=Admin):
    return applicant_out(db.get(Applicant, applicant_id) or _404(), full=True)


class ApplicantPatch(BaseModel):
    status: str | None = None
    notes: str | None = None
    automation_paused: bool | None = None
    human_takeover: bool | None = None
    consent_email: bool | None = None


@router.patch("/applicants/{applicant_id}")
def update_applicant(applicant_id: int, body: ApplicantPatch, db: Session = Depends(get_db), user=Admin):
    a = db.get(Applicant, applicant_id) or _404()
    changes = body.model_dump(exclude_none=True)
    if changes.get("consent_email") is True and a.opted_out_at:
        raise HTTPException(409, "Applicant opted out; consent can only be restored by the applicant")
    for k, v in changes.items():
        setattr(a, k, v)
    if changes.get("consent_email") is False:
        a.opted_out_at = a.opted_out_at or utcnow()
    audit(db, user.email, "applicant_updated", "applicant", a.id, **changes)
    return applicant_out(a, full=True)


# ---------- conversations ----------
@router.get("/conversations")
def conversations(attention: bool = False, db: Session = Depends(get_db), _=Admin):
    rows = []
    for a in db.query(Applicant).join(Message).distinct().all():
        last = a.messages[-1]
        item = {"applicant": applicant_out(a), "last_message": message_out(last),
                "drafts": sum(m.status == "draft" for m in a.messages),
                "escalated": any(m.escalated for m in a.messages if m.direction == "inbound"
                                 and m.id > max([x.id for x in a.messages if x.direction == "outbound"
                                                 and x.status == "sent"] or [0]))}
        if not attention or item["drafts"] or item["escalated"]:
            rows.append(item)
    rows.sort(key=lambda r: r["last_message"]["created_at"], reverse=True)
    return rows


class ManualMessage(BaseModel):
    subject: str = ""
    body: str


@router.post("/applicants/{applicant_id}/messages", status_code=201)
def manual_send(applicant_id: int, body: ManualMessage, db: Session = Depends(get_db), user=Admin):
    a = db.get(Applicant, applicant_id) or _404()
    m = Message(applicant_id=a.id, direction="outbound", status="approved", author=f"admin:{user.email}",
                subject=body.subject or "Re: your application", body=body.body)
    db.add(m)
    db.flush()
    db.refresh(a)
    send_message(db, m, automated=False)
    return message_out(m)


class DraftPatch(BaseModel):
    body: str | None = None
    subject: str | None = None


@router.patch("/messages/{message_id}")
def edit_draft(message_id: int, body: DraftPatch, db: Session = Depends(get_db), user=Admin):
    m = db.get(Message, message_id) or _404()
    if m.status != "draft":
        raise HTTPException(409, "Only drafts can be edited")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    audit(db, user.email, "draft_edited", "message", m.id)
    return message_out(m)


@router.post("/messages/{message_id}/approve")
def approve_draft(message_id: int, db: Session = Depends(get_db), user=Admin):
    m = db.get(Message, message_id) or _404()
    if m.status not in ("draft", "failed"):
        raise HTTPException(409, f"Message is {m.status}")
    m.status = "approved"
    m.author = f"{m.author}+approved:{user.email}"
    db.flush()
    send_message(db, m, automated=False)  # human-approved => pauses don't apply, opt-out still does
    return message_out(m)


@router.post("/messages/{message_id}/discard")
def discard_draft(message_id: int, db: Session = Depends(get_db), user=Admin):
    m = db.get(Message, message_id) or _404()
    if m.status != "draft":
        raise HTTPException(409, "Only drafts can be discarded")
    m.status = "discarded"
    audit(db, user.email, "draft_discarded", "message", m.id)
    return {"ok": True}


@router.post("/messages/{message_id}/resolve")
def resolve_escalation(message_id: int, db: Session = Depends(get_db), user=Admin):
    m = db.get(Message, message_id) or _404()
    m.escalated = False
    audit(db, user.email, "escalation_resolved", "message", m.id)
    return {"ok": True}


# ---------- automation ----------
@router.get("/automation")
def automation_state(db: Session = Depends(get_db), _=Admin):
    s = all_settings(db)
    return {"automation_paused": s["automation_paused"], "auto_send_ai_replies": s["auto_send_ai_replies"],
            "auto_acknowledge": s["auto_acknowledge"],
            "paused_applicants": db.query(Applicant).filter_by(automation_paused=True).count(),
            "opted_out": db.query(Applicant).filter(Applicant.opted_out_at.isnot(None)).count(),
            "rules": [_rule(r) for r in db.query(FollowUpRule).order_by(FollowUpRule.id)]}


class PauseIn(BaseModel):
    paused: bool


@router.post("/automation/pause")
def global_pause(body: PauseIn, db: Session = Depends(get_db), user=Admin):
    set_setting(db, "automation_paused", body.paused)
    audit(db, user.email, "global_pause" if body.paused else "global_resume")
    return {"automation_paused": body.paused}


class RuleIn(BaseModel):
    name: str
    trigger_status: str = "in_review"
    wait_hours: int = 72
    template: str
    max_sends: int = 1
    is_active: bool = True


@router.post("/automation/rules", status_code=201)
def create_rule(body: RuleIn, db: Session = Depends(get_db), user=Admin):
    r = FollowUpRule(**body.model_dump())
    db.add(r)
    db.commit()
    audit(db, user.email, "rule_created", "rule", r.id)
    return _rule(r)


@router.put("/automation/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleIn, db: Session = Depends(get_db), user=Admin):
    r = db.get(FollowUpRule, rule_id) or _404()
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    audit(db, user.email, "rule_updated", "rule", r.id)
    return _rule(r)


def _rule(r: FollowUpRule) -> dict:
    return {"id": r.id, "name": r.name, "trigger_status": r.trigger_status, "wait_hours": r.wait_hours,
            "template": r.template, "max_sends": r.max_sends, "is_active": r.is_active}


# ---------- settings & knowledge base ----------
@router.get("/settings")
def get_settings_api(db: Session = Depends(get_db), _=Admin):
    s = get_settings()
    return {"runtime": all_settings(db), "llm": {"provider": s.llm_provider,
            "model": s.ollama_model if s.llm_provider == "ollama" else s.anthropic_model},
            "open_webui_url": s.open_webui_url}


@router.put("/settings")
def put_settings(body: dict, db: Session = Depends(get_db), user=Admin):
    for k, v in body.items():
        if k not in DEFAULTS:
            raise HTTPException(400, f"Unknown setting {k}")
        set_setting(db, k, v)
    audit(db, user.email, "settings_updated", detail_keys=list(body))
    return all_settings(db)


class ArticleIn(BaseModel):
    title: str
    content: str
    tags: str = ""
    is_active: bool = True


@router.get("/knowledge")
def list_kb(db: Session = Depends(get_db), _=Admin):
    return [{"id": a.id, "title": a.title, "content": a.content, "tags": a.tags, "is_active": a.is_active,
             "updated_at": a.updated_at} for a in db.query(KnowledgeArticle).order_by(KnowledgeArticle.id)]


@router.post("/knowledge", status_code=201)
def create_kb(body: ArticleIn, db: Session = Depends(get_db), user=Admin):
    a = KnowledgeArticle(**body.model_dump())
    db.add(a)
    db.commit()
    audit(db, user.email, "kb_created", "kb", a.id)
    return {"id": a.id}


@router.put("/knowledge/{article_id}")
def update_kb(article_id: int, body: ArticleIn, db: Session = Depends(get_db), user=Admin):
    a = db.get(KnowledgeArticle, article_id) or _404()
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    audit(db, user.email, "kb_updated", "kb", a.id)
    return {"ok": True}


class AITestIn(BaseModel):
    message: str
    applicant_id: int | None = None


@router.post("/ai/test")
def ai_test(body: AITestIn, db: Session = Depends(get_db), _=Admin):
    """Dry-run the guarded reply engine (nothing is stored or sent)."""
    a = db.get(Applicant, body.applicant_id) if body.applicant_id else Applicant(full_name="Test Applicant", status="new")
    if a is None:
        _404()
    try:
        d = ai_engine.draft_reply(db, a, body.message)
    except Exception as exc:
        raise HTTPException(503, f"AI unavailable: {exc}")
    return d.__dict__


# ---------- system ----------
@router.get("/health")
def health(db: Session = Depends(get_db)):
    db_ok = True
    try:
        db.execute(text("select 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok,
            "llm": get_provider().health(), "llm_provider": get_provider().name}


@router.get("/stats")
def stats(db: Session = Depends(get_db), _=Admin):
    q = db.query
    return {"applicants": q(Applicant).count(), "applications": q(Application).count(),
            "pending_ai": q(Application).filter(Application.processing_status.in_(["pending", "failed"])).count(),
            "needs_review": q(Application).filter_by(processing_status="needs_review").count(),
            "duplicates": q(Application).filter_by(is_duplicate=True).count(),
            "drafts": q(Message).filter_by(status="draft").count(),
            "escalated": q(Message).filter_by(escalated=True).count(),
            "failed_deliveries": q(Message).filter_by(status="failed").count()}


@router.get("/audit")
def audit_log(limit: int = 200, db: Session = Depends(get_db), _=Admin):
    return [{"id": x.id, "actor": x.actor, "action": x.action, "entity": x.entity, "entity_id": x.entity_id,
             "detail": x.detail, "created_at": x.created_at}
            for x in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))]


def _404():
    raise HTTPException(404, "Not found")
