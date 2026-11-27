"""Runtime settings editable from the dashboard (stored in DB, not env)."""
from sqlalchemy.orm import Session

from ..models import SystemSetting

DEFAULTS: dict[str, object] = {
    "automation_paused": False,       # global kill switch for ALL outbound automation
    "auto_send_ai_replies": False,    # False = AI replies wait in the review queue
    "auto_acknowledge": True,         # send templated acknowledgment on new application
    "confidence_threshold": 0.7,      # below this, AI escalates to a human
    "company_name": "Acme Staffing",
    "ack_subject": "We received your application – {company}",
    "ack_template": (
        "Hi {first_name},\n\nThank you for applying for {position} at {company}. "
        "We have received your application and our recruitment team will review it shortly.\n\n"
        "You can reply to this email at any time with questions. "
        "To stop receiving emails from us, reply with UNSUBSCRIBE.\n\nKind regards,\n{company} Recruitment"
    ),
    "system_prompt_extra": "",
}


def get_setting(db: Session, key: str):
    row = db.get(SystemSetting, key)
    return row.value["v"] if row else DEFAULTS.get(key)


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(SystemSetting, key)
    if row:
        row.value = {"v": value}
    else:
        db.add(SystemSetting(key=key, value={"v": value}))
    db.commit()


def all_settings(db: Session) -> dict:
    return {k: get_setting(db, k) for k in DEFAULTS}
