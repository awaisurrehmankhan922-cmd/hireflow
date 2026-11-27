"""Background processing: applications (ack + AI triage) and inbound messages (AI reply drafts)."""
import logging
import re

from sqlalchemy.orm import Session

from ..llm import LLMUnavailable
from ..models import Applicant, Application, Message, utcnow
from . import ai_engine
from .audit import audit
from .mailer import send_message
from .settings_store import get_setting

log = logging.getLogger("hireflow.processing")
MAX_ATTEMPTS = 8
OPT_OUT = re.compile(r"^\s*(unsubscribe|stop)\b|\b(opt[- ]?out|remove me from|stop (emailing|contacting) me)\b", re.I)


def _fmt(template: str, applicant: Applicant, position: str, company: str) -> str:
    first = (applicant.full_name or "there").split()[0]
    return template.format(first_name=first, full_name=applicant.full_name, position=position or "the role",
                           company=company)


def send_acknowledgment(db: Session, app: Application) -> None:
    if app.acknowledged_at or app.is_duplicate or not get_setting(db, "auto_acknowledge"):
        return
    company = get_setting(db, "company_name")
    msg = Message(applicant_id=app.applicant_id, direction="outbound", status="approved", author="system",
                  subject=_fmt(get_setting(db, "ack_subject"), app.applicant, app.position, company),
                  body=_fmt(get_setting(db, "ack_template"), app.applicant, app.position, company))
    db.add(msg)
    db.flush()
    db.refresh(app.applicant)
    send_message(db, msg)
    if msg.status == "sent":
        app.acknowledged_at = utcnow()
    db.commit()


def process_application(db: Session, app: Application) -> str:
    send_acknowledgment(db, app)  # templated, independent of AI availability
    if app.processing_status not in ("pending", "failed"):
        return app.processing_status
    app.processing_attempts += 1
    try:
        cls, summary, conf = ai_engine.classify_application(db, app.payload, app.position)
    except LLMUnavailable as exc:
        app.last_error = str(exc)[:500]  # stays pending, retried after recovery
        db.commit()
        return "pending"
    except Exception as exc:
        app.last_error = str(exc)[:500]
        app.processing_status = "failed" if app.processing_attempts < MAX_ATTEMPTS else "needs_review"
        db.commit()
        return app.processing_status
    app.classification, app.ai_summary, app.ai_confidence = cls, summary, conf
    app.processing_status = "processed" if conf >= float(get_setting(db, "confidence_threshold")) else "needs_review"
    app.last_error = ""
    if app.applicant.status == "new":
        app.applicant.status = "in_review"
    audit(db, "ai", "application_classified", "application", app.id, classification=cls, confidence=conf)
    return app.processing_status


def process_pending_applications(db: Session, limit: int = 50) -> int:
    apps = (db.query(Application).filter(Application.processing_status.in_(["pending", "failed"]))
            .order_by(Application.id).limit(limit).all())
    # also retry acknowledgments that failed delivery earlier
    apps += [a for a in db.query(Application).filter(Application.acknowledged_at.is_(None),
             Application.is_duplicate.is_(False), Application.processing_status.notin_(["pending", "failed"])).limit(limit)]
    done = 0
    for app in apps:
        if process_application(db, app) != "pending":
            done += 1
    return done


def handle_inbound(db: Session, msg: Message) -> None:
    """Opt-out first, then AI draft. Auto-send only when allowed and confident."""
    applicant = msg.applicant
    if OPT_OUT.search(msg.body or "") or OPT_OUT.search(msg.subject or ""):
        applicant.opted_out_at, applicant.consent_email = utcnow(), False
        msg.classification = "opt_out"
        audit(db, "system", "opt_out", "applicant", applicant.id, source_message=msg.id)
        return
    if applicant.human_takeover:
        msg.classification = "awaiting_human"
        db.commit()
        return
    try:
        d = ai_engine.draft_reply(db, applicant, msg.body)
    except LLMUnavailable:
        msg.classification = "pending_ai"
        db.commit()
        return
    except Exception as exc:
        msg.classification, msg.escalated, msg.escalation_reason = "error", True, str(exc)[:200]
        db.commit()
        return
    msg.classification, msg.ai_confidence = d.intent, d.confidence
    if d.needs_human:
        msg.escalated, msg.escalation_reason = True, d.reason
        audit(db, "ai", "escalated", "message", msg.id, reason=d.reason)
        db.commit()
        return
    draft = Message(applicant_id=applicant.id, direction="outbound", status="draft", author="ai",
                    subject=_reply_subject(msg.subject), body=d.reply, classification=d.intent,
                    ai_confidence=d.confidence)
    db.add(draft)
    db.flush()
    db.refresh(applicant)
    if get_setting(db, "auto_send_ai_replies"):
        draft.status = "approved"
        send_message(db, draft)
    db.commit()


def process_pending_inbound(db: Session) -> int:
    msgs = db.query(Message).filter(Message.direction == "inbound",
                                    Message.classification.in_(["", "pending_ai"])).order_by(Message.id).all()
    for m in msgs:
        handle_inbound(db, m)
    db.commit()
    return len(msgs)


def _reply_subject(subject: str) -> str:
    subject = subject or "Your application"
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"
