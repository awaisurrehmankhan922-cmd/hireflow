"""Application intake. Deliberately has NO dependency on the AI service, so applications are
always accepted and stored (status=pending) even when inference is down."""
import hashlib
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import Applicant, Application, utcnow
from .audit import audit

DUPLICATE_WINDOW_DAYS = 30


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def fingerprint(email: str, position: str) -> str:
    return hashlib.sha256(f"{normalise_email(email)}|{position.strip().lower()}".encode()).hexdigest()


def ingest_application(db: Session, *, source: str, external_id: str, email: str, full_name: str,
                       phone: str = "", position: str = "", fields: dict | None = None) -> tuple[Application, bool]:
    """Returns (application, created). Re-delivery of the same external_id is idempotent."""
    email = normalise_email(email)
    if not email or "@" not in email:
        raise ValueError("valid email is required")

    existing = db.query(Application).filter_by(source=source, external_id=external_id).first()
    if existing:
        return existing, False

    applicant = db.query(Applicant).filter_by(email=email).first()
    if not applicant:
        applicant = Applicant(email=email, full_name=full_name.strip(), phone=phone.strip())
        db.add(applicant)
        db.flush()
    else:  # returning contact: enrich missing details only
        applicant.full_name = applicant.full_name or full_name.strip()
        applicant.phone = applicant.phone or phone.strip()

    fp = fingerprint(email, position)
    window_start = utcnow() - timedelta(days=DUPLICATE_WINDOW_DAYS)
    prior = (db.query(Application)
             .filter(Application.fingerprint == fp, Application.is_duplicate.is_(False))
             .order_by(Application.id.desc()).first())
    is_dup = bool(prior and _aware(prior.received_at) >= window_start)

    app = Application(applicant_id=applicant.id, source=source, external_id=external_id, position=position,
                      payload=fields or {}, fingerprint=fp, is_duplicate=is_dup,
                      duplicate_of_id=prior.id if is_dup else None,
                      processing_status="duplicate" if is_dup else "pending")
    db.add(app)
    db.flush()
    audit(db, f"intake:{source}", "application_received", "application", app.id,
          applicant_id=applicant.id, duplicate=is_dup)
    return app, True


def _aware(dt):
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
