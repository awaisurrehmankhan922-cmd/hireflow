from .models import Applicant, Application, Message


def message_out(m: Message) -> dict:
    return {"id": m.id, "applicant_id": m.applicant_id, "direction": m.direction, "status": m.status,
            "author": m.author, "subject": m.subject, "body": m.body, "classification": m.classification,
            "ai_confidence": m.ai_confidence, "escalated": m.escalated, "escalation_reason": m.escalation_reason,
            "error": m.error, "created_at": m.created_at, "sent_at": m.sent_at}


def application_out(a: Application) -> dict:
    return {"id": a.id, "source": a.source, "external_id": a.external_id, "position": a.position,
            "payload": a.payload, "is_duplicate": a.is_duplicate, "duplicate_of_id": a.duplicate_of_id,
            "processing_status": a.processing_status, "classification": a.classification,
            "ai_summary": a.ai_summary, "ai_confidence": a.ai_confidence, "acknowledged_at": a.acknowledged_at,
            "received_at": a.received_at, "last_error": a.last_error}


def applicant_out(a: Applicant, full: bool = False) -> dict:
    originals = [x for x in a.applications if not x.is_duplicate] or a.applications
    latest = originals[-1] if originals else None
    d = {"id": a.id, "email": a.email, "full_name": a.full_name, "phone": a.phone, "status": a.status,
         "consent_email": a.consent_email, "opted_out_at": a.opted_out_at, "automation_paused": a.automation_paused,
         "human_takeover": a.human_takeover, "email_verified": a.email_verified, "created_at": a.created_at,
         "classification": latest.classification if latest else "", "position": latest.position if latest else "",
         "applications_count": len(a.applications),
         "needs_attention": any(m.escalated for m in a.messages[-5:]) or any(m.status == "draft" for m in a.messages)}
    if full:
        d |= {"notes": a.notes, "applications": [application_out(x) for x in a.applications],
              "messages": [message_out(m) for m in a.messages]}
    return d
