"""Inbound email: IMAP polling, applicant matching, threading and duplicate prevention."""
import email
import imaplib
import logging
from email.header import decode_header, make_header
from email.utils import parseaddr

from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Applicant, Message, utcnow
from .audit import audit
from .intake import normalise_email

log = logging.getLogger("hireflow.inbox")


def _text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")


def strip_quoted(body: str) -> str:
    """Keep only the new part of a reply (drop '>' quotes and 'On ... wrote:' blocks)."""
    out = []
    for line in body.splitlines():
        if line.startswith(">") or (line.startswith("On ") and line.rstrip().endswith("wrote:")):
            break
        out.append(line)
    return "\n".join(out).strip()


def record_inbound(db: Session, *, from_addr: str, subject: str, body: str, message_id: str,
                   in_reply_to: str = "") -> Message | None:
    """Store an inbound email once. Returns None if already processed or sender unknown."""
    if message_id and db.query(Message).filter_by(email_message_id=message_id).first():
        return None  # duplicate delivery / re-poll
    sender = normalise_email(parseaddr(from_addr)[1])
    applicant = db.query(Applicant).filter_by(email=sender).first()
    if not applicant and in_reply_to:  # sender changed address but replied in-thread
        parent = db.query(Message).filter_by(email_message_id=in_reply_to).first()
        applicant = parent.applicant if parent else None
    if not applicant:  # unknown contact -> create a lead record so nothing is lost
        applicant = Applicant(email=sender, full_name=parseaddr(from_addr)[0], status="new")
        db.add(applicant)
        db.flush()
    msg = Message(applicant_id=applicant.id, direction="inbound", status="received", author="applicant",
                  subject=subject[:500], body=strip_quoted(body) or body, email_message_id=message_id or None,
                  in_reply_to=in_reply_to)
    applicant.last_inbound_at = utcnow()
    applicant.email_verified = True  # they control the mailbox
    db.add(msg)
    db.flush()
    db.refresh(applicant)
    audit(db, "inbox", "email_received", "message", msg.id, applicant_id=applicant.id)
    return msg


def poll_imap(db: Session) -> int:
    s = get_settings()
    if not s.imap_host:
        return 0
    count = 0
    with imaplib.IMAP4_SSL(s.imap_host, s.imap_port) as imap:
        imap.login(s.imap_user, s.imap_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _, raw = imap.fetch(num, "(RFC822)")
            m = email.message_from_bytes(raw[0][1])
            if record_inbound(db, from_addr=m.get("From", ""), subject=str(make_header(decode_header(m.get("Subject", "")))),
                              body=_text_body(m), message_id=m.get("Message-ID", "").strip(),
                              in_reply_to=m.get("In-Reply-To", "").strip()):
                count += 1
            imap.store(num, "+FLAGS", "\\Seen")
        db.commit()
    return count
