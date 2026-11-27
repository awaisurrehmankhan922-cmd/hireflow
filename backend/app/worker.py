"""Background worker (separate container). Each loop:
  1. polls the designated mailbox (IMAP)
  2. processes pending applications (incl. anything queued during an AI outage)
  3. drafts/sends replies for new inbound messages
  4. runs follow-up workflows
Failures in one step never stop the others; the loop always continues."""
import logging
import time

from .config import get_settings
from .db import SessionLocal
from .main import bootstrap
from .services import followups, inbox, processing

log = logging.getLogger("hireflow.worker")


def run_once() -> dict:
    out = {}
    for name, fn in (("emails", inbox.poll_imap), ("applications", processing.process_pending_applications),
                     ("inbound", processing.process_pending_inbound), ("followups", followups.run_follow_ups)):
        db = SessionLocal()
        try:
            out[name] = fn(db)
            db.commit()
        except Exception:
            db.rollback()
            log.exception("worker step %s failed", name)
            out[name] = "error"
        finally:
            db.close()
    return out


def main() -> None:
    bootstrap()
    interval = get_settings().worker_interval_seconds
    log.info("worker started, interval=%ss", interval)
    while True:
        log.info("cycle %s", run_once())
        time.sleep(interval)


if __name__ == "__main__":
    main()
