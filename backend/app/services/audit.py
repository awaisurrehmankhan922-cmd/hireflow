import logging

from sqlalchemy.orm import Session

from ..models import AuditLog

log = logging.getLogger("hireflow")


def audit(db: Session, actor: str, action: str, entity: str = "", entity_id="", commit: bool = True, **detail):
    db.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=str(entity_id), detail=detail))
    log.info("audit actor=%s action=%s %s:%s %s", actor, action, entity, entity_id, detail)
    if commit:
        db.commit()
