"""Outbound email: one permission gate for every automated send, plus SMTP transport."""
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Applicant, Message, utcnow
from .audit import audit
from .settings_store import get_setting


class SMTPTransport:
    def send(self, to: str, subject: str, body: str, in_reply_to: str = "") -> str:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
        msg["Message-ID"] = make_msgid(domain=s.mail_from.split("@")[-1])
        if in_reply_to:
            msg["In-Reply-To"] = msg["References"] = in_reply_to
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return msg["Message-ID"]


class MemoryTransport:
    """Captures mail in memory (tests/demo). Set `fail=True` to simulate delivery failure."""

    def __init__(self):
        self.outbox: list[dict] = []
        self.fail = False

    def send(self, to, subject, body, in_reply_to=""):
        if self.fail:
            raise smtplib.SMTPException("simulated delivery failure")
        mid = f"<{uuid.uuid4()}@hireflow.test>"
        self.outbox.append({"to": to, "subject": subject, "body": body, "message_id": mid, "in_reply_to": in_reply_to})
        return mid


_transport = None


def get_transport():
    global _transport
    if _transport is None:
        _transport = MemoryTransport() if get_settings().mail_transport == "log" else SMTPTransport()
    return _transport


def set_transport(t) -> None:
    global _transport
    _transport = t


def automation_block_reason(db: Session, applicant: Applicant) -> str | None:
    """Returns why automated mail may NOT be sent, or None if allowed."""
    if get_setting(db, "automation_paused"):
        return "global automation pause"
    if applicant.opted_out_at or not applicant.consent_email:
        return "applicant opted out / no consent"
    if applicant.automation_paused:
        return "applicant automation paused"
    if applicant.human_takeover:
        return "human takeover active"
    return None


def send_message(db: Session, msg: Message, automated: bool = True) -> Message:
    """Send an outbound Message row. Manual admin sends bypass pauses but NEVER opt-outs."""
    applicant = msg.applicant
    reason = automation_block_reason(db, applicant) if automated else (
        "applicant opted out" if applicant.opted_out_at else None)
    if reason:
        msg.status, msg.error = "blocked", reason
        audit(db, "system", "send_blocked", "message", msg.id, reason=reason)
        return msg
    last_in = next((m for m in reversed(applicant.messages) if m.direction == "inbound" and m.email_message_id), None)
    try:
        mid = get_transport().send(applicant.email, msg.subject, msg.body, last_in.email_message_id if last_in else "")
        msg.status, msg.email_message_id, msg.sent_at, msg.error = "sent", mid, utcnow(), ""
        applicant.last_outbound_at = msg.sent_at
        audit(db, msg.author, "message_sent", "message", msg.id, to=applicant.email)
    except Exception as exc:  # record delivery failures, keep row for retry
        msg.status, msg.error = "failed", str(exc)[:500]
        audit(db, "system", "delivery_failed", "message", msg.id, error=str(exc)[:200])
    db.commit()
    return msg
