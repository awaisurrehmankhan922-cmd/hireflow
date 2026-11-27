"""Configurable follow-up workflows (e.g. "no reply 72h after acknowledgment -> nudge once")."""
from datetime import timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Applicant, FollowUpLog, FollowUpRule, Message, utcnow
from .mailer import automation_block_reason, send_message
from .settings_store import get_setting


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_follow_ups(db: Session, now=None) -> int:
    if get_setting(db, "automation_paused"):
        return 0
    now = now or utcnow()
    sent = 0
    for rule in db.query(FollowUpRule).filter_by(is_active=True).all():
        for a in db.query(Applicant).filter_by(status=rule.trigger_status).all():
            if automation_block_reason(db, a):
                continue
            last_out = _aware(a.last_outbound_at)
            if not last_out or (a.last_inbound_at and _aware(a.last_inbound_at) > last_out):
                continue  # nothing to follow up, or they already replied
            if now - last_out < timedelta(hours=rule.wait_hours):
                continue
            n = db.query(FollowUpLog).filter_by(rule_id=rule.id, applicant_id=a.id).count()
            if n >= rule.max_sends:
                continue
            first = (a.full_name or "there").split()[0]
            msg = Message(applicant_id=a.id, direction="outbound", status="approved", author="system",
                          subject=f"Following up – {get_setting(db, 'company_name')}",
                          body=rule.template.format(first_name=first, company=get_setting(db, "company_name")))
            db.add(msg)
            db.flush()
            db.refresh(a)
            send_message(db, msg)
            db.add(FollowUpLog(rule_id=rule.id, applicant_id=a.id, sequence=n + 1, message_id=msg.id))
            db.commit()
            sent += msg.status == "sent"
    return sent
