"""Acceptance tests – one test per workflow in the client's acceptance criteria (numbered 1–14)."""
import json

from app.llm.providers import MockProvider
from app.models import Application, Message
from app.services import processing
from app.services.inbox import record_inbound
from tests.conftest import sign


def _inbound(db, body, sender="Maria Santos <MARIA@example.com>", mid="<in-1@mail.example.com>", subject="Question"):
    m = record_inbound(db, from_addr=sender, subject=subject, body=body, message_id=mid)
    db.commit()
    if m:
        processing.handle_inbound(db, m)
        db.commit()
    return m


# 1 + 2 ---------------------------------------------------------------------------------------
def test_01_02_wordpress_application_received_and_stored(client, submit):
    r = submit()
    assert r.status_code == 202 and r.json()["created"] is True
    a = client.get(f"/api/applicants/{r.json()['applicant_id']}").json()
    assert a["email"] == "maria@example.com"
    assert a["applications"][0]["position"] == "Housekeeping Supervisor"


def test_webhook_rejects_bad_signature_and_replay(client):
    body = json.dumps({"entry_id": "1", "email": "x@y.com"}).encode()
    assert client.post("/api/webhooks/wordpress", content=body, headers=sign(body, secret="wrong")).status_code == 401
    assert client.post("/api/webhooks/wordpress", content=body, headers=sign(body, ts=1_000_000)).status_code == 401


def test_webhook_validates_email(submit):
    assert submit(email="not-an-email").status_code == 422


# 3 -------------------------------------------------------------------------------------------
def test_03_duplicates_identified(client, submit):
    first = submit(entry_id="1").json()
    redelivery = submit(entry_id="1").json()          # same WP entry re-sent (retry) -> idempotent
    assert redelivery["created"] is False and redelivery["application_id"] == first["application_id"]
    dup = submit(entry_id="2", email=" Maria@Example.com ").json()  # same person+role, new entry
    assert dup["duplicate"] is True and dup["applicant_id"] == first["applicant_id"]
    other_role = submit(entry_id="3", position="Front Desk Agent").json()
    assert other_role["duplicate"] is False
    assert client.get("/api/stats").json()["duplicates"] == 1


# 4 + 5 ---------------------------------------------------------------------------------------
def test_04_05_ai_classifies_and_acknowledgment_sent(client, submit, outbox):
    r = submit().json()
    app = client.get(f"/api/applicants/{r['applicant_id']}").json()["applications"][0]
    assert app["processing_status"] == "processed"
    assert app["classification"] == "qualified" and app["ai_confidence"] >= 0.7
    assert app["acknowledged_at"] is not None
    assert len(outbox.outbox) == 1 and outbox.outbox[0]["to"] == "maria@example.com"
    assert "Housekeeping Supervisor" in outbox.outbox[0]["body"]


def test_duplicate_gets_no_second_acknowledgment(submit, outbox):
    submit(entry_id="1")
    submit(entry_id="2")
    assert len(outbox.outbox) == 1


# 6 + 7 + 8 -----------------------------------------------------------------------------------
def test_06_07_08_inbound_email_recognised_associated_and_visible(client, submit, db):
    applicant_id = submit().json()["applicant_id"]
    m = _inbound(db, "Hi, what is the status of my application?")
    assert m.applicant_id == applicant_id  # matched despite upper-case sender address
    convo = client.get("/api/conversations").json()
    assert convo[0]["applicant"]["id"] == applicant_id
    msgs = client.get(f"/api/applicants/{applicant_id}").json()["messages"]
    assert [x["direction"] for x in msgs] == ["outbound", "inbound", "outbound"]  # ack, question, AI draft
    assert msgs[-1]["status"] == "draft" and msgs[-1]["author"] == "ai"


def test_inbound_duplicate_processing_prevented(submit, db):
    submit()
    assert _inbound(db, "hello") is not None
    assert _inbound(db, "hello") is None  # same Message-ID re-polled
    assert db.query(Message).filter_by(direction="inbound").count() == 1


def test_reply_in_thread_from_new_address_matched(submit, db, outbox):
    applicant_id = submit().json()["applicant_id"]
    ack_mid = outbox.outbox[0]["message_id"]
    m = record_inbound(db, from_addr="maria.work@company.com", subject="Re: ack", body="Thanks",
                       message_id="<x@y>", in_reply_to=ack_mid)
    assert m.applicant_id == applicant_id


# 9 -------------------------------------------------------------------------------------------
def test_09_admin_reviews_approves_and_takes_over(client, submit, db, outbox):
    aid = submit().json()["applicant_id"]
    _inbound(db, "When will I hear back?")
    draft = client.get(f"/api/applicants/{aid}").json()["messages"][-1]
    client.patch(f"/api/messages/{draft['id']}", json={"body": draft["body"] + "\n\n(edited by recruiter)"})
    sent = client.post(f"/api/messages/{draft['id']}/approve").json()
    assert sent["status"] == "sent" and "edited by recruiter" in outbox.outbox[-1]["body"]

    client.patch(f"/api/applicants/{aid}", json={"human_takeover": True})
    _inbound(db, "One more question", mid="<in-2@mail>")
    msgs = client.get(f"/api/applicants/{aid}").json()["messages"]
    assert msgs[-1]["direction"] == "inbound"  # AI stayed silent under takeover
    manual = client.post(f"/api/applicants/{aid}/messages", json={"body": "Hi Maria, I'll call you today."}).json()
    assert manual["status"] == "sent" and manual["author"].startswith("admin:")


def test_sensitive_question_escalates_to_human(client, submit, db):
    aid = submit().json()["applicant_id"]
    m = _inbound(db, "Am I eligible for visa sponsorship?")
    assert m.escalated and "sensitive" in m.escalation_reason
    assert client.get(f"/api/applicants/{aid}").json()["messages"][-1]["direction"] == "inbound"  # no draft


def test_auto_send_only_when_enabled(client, submit, db, outbox):
    submit()
    client.put("/api/settings", json={"auto_send_ai_replies": True})
    _inbound(db, "What's the status of my application?")
    assert len(outbox.outbox) == 2 and outbox.outbox[-1]["in_reply_to"] == "<in-1@mail.example.com>"


# 10 ------------------------------------------------------------------------------------------
def test_10_global_pause_stops_all_automation(client, submit, outbox):
    client.post("/api/automation/pause", json={"paused": True})
    r = submit().json()
    assert outbox.outbox == []  # acknowledgment blocked
    msgs = client.get(f"/api/applicants/{r['applicant_id']}").json()["messages"]
    assert msgs[0]["status"] == "blocked" and msgs[0]["error"] == "global automation pause"


def test_10_individual_pause_and_opt_out_enforced_immediately(client, submit, db, outbox):
    aid = submit().json()["applicant_id"]
    client.put("/api/settings", json={"auto_send_ai_replies": True})
    client.patch(f"/api/applicants/{aid}", json={"automation_paused": True})
    _inbound(db, "status?")
    assert len(outbox.outbox) == 1  # only the original ack
    client.patch(f"/api/applicants/{aid}", json={"automation_paused": False})

    _inbound(db, "UNSUBSCRIBE", mid="<in-3@mail>")
    a = client.get(f"/api/applicants/{aid}").json()
    assert a["opted_out_at"] and a["consent_email"] is False
    manual = client.post(f"/api/applicants/{aid}/messages", json={"body": "hi"}).json()
    assert manual["status"] == "blocked"  # even admins cannot email an opted-out applicant
    assert client.patch(f"/api/applicants/{aid}", json={"consent_email": True}).status_code == 409


# 11 + 12 -------------------------------------------------------------------------------------
def test_11_12_applications_accepted_during_ai_outage_and_processed_after(client, submit, db, outbox):
    MockProvider.available = False
    r = submit()
    assert r.status_code == 202  # still accepted
    app = db.get(Application, r.json()["application_id"])
    assert app.processing_status == "pending" and "outage" in app.last_error
    assert len(outbox.outbox) == 1  # templated acknowledgment does not depend on the AI

    MockProvider.available = True  # service recovers -> worker cycle
    processing.process_pending_applications(db)
    db.refresh(app)
    assert app.processing_status == "processed" and app.classification == "qualified"
    assert len(outbox.outbox) == 1  # no double ack


def test_delivery_failure_recorded_and_retried(client, submit, db, outbox):
    outbox.fail = True
    r = submit().json()
    msg = client.get(f"/api/applicants/{r['applicant_id']}").json()["messages"][0]
    assert msg["status"] == "failed" and "simulated" in msg["error"]
    assert client.get("/api/stats").json()["failed_deliveries"] == 1
    outbox.fail = False
    processing.process_pending_applications(db)
    assert len(outbox.outbox) == 1


# 13 + 14 -------------------------------------------------------------------------------------
def test_13_open_webui_gated_by_dashboard_login(client):
    r = client.get("/api/auth/verify")
    assert r.status_code == 200 and r.headers["X-User-Email"] == "admin@test.com"
    client.headers.pop("Authorization")
    client.cookies.clear()
    assert client.get("/api/auth/verify").status_code == 401
    assert client.get("/api/settings").status_code == 401


def test_14_settings_expose_open_webui_and_llm(client):
    s = client.get("/api/settings").json()
    assert s["open_webui_url"] and s["llm"]["provider"] == "mock"
    assert client.get("/api/health").json()["llm"] is True


# extras --------------------------------------------------------------------------------------
def test_ai_never_states_decisions(client):
    from app.services import ai_engine

    class Bad(MockProvider):
        def complete(self, system, prompt, json_mode=False):
            return json.dumps({"intent": "status", "reply": "Great news, you have been hired!", "confidence": 0.99,
                               "needs_human": False})
    from app.llm.factory import set_provider
    set_provider(Bad())
    d = client.post("/api/ai/test", json={"message": "any news?"}).json()
    assert d["needs_human"] is True and "decision" in d["reason"]
    assert ai_engine.FORBIDDEN_OUTPUT.search("you are not eligible")


def test_follow_up_sent_once_after_silence(client, submit, db, outbox):
    from datetime import timedelta

    from app.models import utcnow
    from app.services.followups import run_follow_ups
    submit()
    later = utcnow() + timedelta(hours=80)
    assert run_follow_ups(db, now=later) == 1
    assert run_follow_ups(db, now=later) == 0  # max_sends respected
    assert "checking in" in outbox.outbox[-1]["body"]


def test_audit_log_records_actions(client, submit):
    submit()
    client.post("/api/automation/pause", json={"paused": True})
    actions = {x["action"] for x in client.get("/api/audit").json()}
    assert {"login", "application_received", "message_sent", "global_pause"} <= actions
