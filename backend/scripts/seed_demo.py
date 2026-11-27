"""Seed realistic demo data by driving the REAL pipeline end-to-end over HTTP:
signed WordPress webhooks -> intake -> AI triage -> acknowledgments, then inbound emails -> AI drafts.

Usage:  python scripts/seed_demo.py http://localhost:8000
(Run the API with MAIL_TRANSPORT=log so demo mail isn't actually delivered.)"""
import hashlib
import hmac
import json
import os
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SECRET = os.environ.get("WEBHOOK_SECRET", "change-me-webhook")

APPLICANTS = [
    ("1001", "maria.santos@example.com", "Maria Santos", "Housekeeping Supervisor", "6 years hotel housekeeping, team lead"),
    ("1002", "ahmed.k@example.com", "Ahmed Khalil", "Front Desk Agent", "3 years experience in guest relations"),
    ("1003", "j.okafor@example.com", "John Okafor", "Line Cook", ""),
    ("1004", "priya.n@example.com", "Priya Nair", "Spa Therapist", "8 years experience, certified"),
    ("1005", "maria.santos@example.com", "Maria Santos", "Housekeeping Supervisor", "6 years (re-submitted)"),
    ("1006", "lucas.m@example.com", "Lucas Moreau", "Concierge", "5 years experience in luxury hotels"),
]
INBOUND = [
    ("ahmed.k@example.com", "Re: We received your application", "Hi, thanks! How long does the review usually take?"),
    ("priya.n@example.com", "Question", "Hello, can your company sponsor my work visa if I am selected?"),
    ("j.okafor@example.com", "Re: We received your application", "UNSUBSCRIBE"),
    ("lucas.m@example.com", "Updated CV", "Hi, can I send an updated CV? What format do you accept?"),
]


def signed_post(path: str, payload: dict):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    sig = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return httpx.post(BASE + path, content=body, headers={"Content-Type": "application/json",
                      "X-HireFlow-Timestamp": ts, "X-HireFlow-Signature": sig})


def main():
    for entry, email, name, pos, exp in APPLICANTS:
        r = signed_post("/api/webhooks/wordpress", {"entry_id": entry, "form_id": "careers", "email": email,
                        "full_name": name, "phone": "+971 50 000 0000", "position": pos,
                        "fields": {"experience": exp, "availability": "Immediate"}})
        print("application", entry, r.status_code, r.json())
    time.sleep(1)
    # inbound mail is normally picked up by the IMAP worker; here we inject via the service layer
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from app.db import SessionLocal
    from app.services.inbox import record_inbound
    from app.services.processing import handle_inbound
    db = SessionLocal()
    for i, (sender, subject, body) in enumerate(INBOUND):
        m = record_inbound(db, from_addr=sender, subject=subject, body=body, message_id=f"<demo-{i}@mail.example.com>")
        db.commit()
        if m:
            handle_inbound(db, m)
            db.commit()
            print("inbound", sender, "->", m.classification, "escalated" if m.escalated else "")
    db.close()


if __name__ == "__main__":
    main()
