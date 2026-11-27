"""Controlled AI conversation engine.

Design rules (enforced in code, not just in the prompt):
  * The model only drafts; it never decides eligibility, hiring or rejection.
  * Every answer is grounded in the editable knowledge base.
  * Low confidence, sensitive topics or forbidden phrasing => escalate to a human.
"""
import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..llm import get_provider
from ..models import Applicant, KnowledgeArticle
from .settings_store import get_setting

SENSITIVE = re.compile(
    r"\b(visa|work permit|sponsor\w*|legal|lawyer|eligib\w*|discriminat\w*|complain\w*|salary negotiation|"
    r"contract terms|immigration|criminal record|disab\w*|pregnan\w*)\b", re.I)
FORBIDDEN_OUTPUT = re.compile(
    r"\b(you (are|have been) (hired|rejected|selected|accepted)|you are (not )?eligible|"
    r"we guarantee|offer of employment)\b", re.I)

BASE_SYSTEM = """You are the recruitment assistant for {company}.
You help applicants with routine questions using ONLY the knowledge base provided.
Hard rules:
- Never make or imply hiring, rejection, legal or eligibility decisions.
- Never invent facts, dates, salaries or policies not in the knowledge base.
- If the answer is not in the knowledge base, or the topic is legal/eligibility/visa/complaint,
  set needs_human=true and leave reply empty.
- Be concise, warm and professional. Sign off as "{company} Recruitment".
{extra}"""


@dataclass
class ReplyDecision:
    intent: str
    reply: str
    confidence: float
    needs_human: bool
    reason: str


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("model did not return JSON")
    return json.loads(m.group(0))


def retrieve_knowledge(db: Session, query: str, k: int = 3) -> list[KnowledgeArticle]:
    """Lightweight keyword-overlap retrieval; swap for pgvector embeddings when the KB grows."""
    words = {w for w in re.findall(r"[a-z]{3,}", query.lower())}
    scored = []
    for art in db.query(KnowledgeArticle).filter(KnowledgeArticle.is_active.is_(True)).all():
        text = f"{art.title} {art.tags} {art.content}".lower()
        score = sum(1 for w in words if w in text)
        scored.append((score, art))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [a for s, a in scored[:k] if s > 0] or [a for _, a in scored[:1]]


def _system(db: Session) -> str:
    return BASE_SYSTEM.format(company=get_setting(db, "company_name"),
                              extra=get_setting(db, "system_prompt_extra") or "")


def classify_application(db: Session, payload: dict, position: str) -> tuple[str, str, float]:
    prompt = (
        "TASK: classify_application\n"
        f"Position: {position}\nApplication fields (JSON): {json.dumps(payload)[:4000]}\n\n"
        'Return JSON {"classification": one of ["qualified","needs_info","incomplete","spam"], '
        '"summary": "2 sentence neutral summary for the recruiter", "confidence": 0-1}. '
        "This is triage for a human recruiter, not a decision."
    )
    data = _parse_json(get_provider().complete(_system(db), prompt, json_mode=True))
    return str(data.get("classification", "needs_info")), str(data.get("summary", "")), float(data.get("confidence", 0))


def draft_reply(db: Session, applicant: Applicant, inbound_text: str) -> ReplyDecision:
    kb = retrieve_knowledge(db, inbound_text)
    history = "\n".join(f"[{m.direction}] {m.body[:500]}" for m in applicant.messages[-6:])
    prompt = (
        "TASK: reply\n"
        "KNOWLEDGE BASE:\n" + "\n---\n".join(f"{a.title}: {a.content}" for a in kb) +
        f"\n\nAPPLICANT: {applicant.full_name} (status: {applicant.status})"
        f"\nRECENT HISTORY:\n{history}\n\nLATEST MESSAGE FROM APPLICANT:\n{inbound_text[:4000]}\n\n"
        'Return JSON {"intent": "...", "reply": "...", "confidence": 0-1, "needs_human": bool, "reason": "..."}'
    )
    data = _parse_json(get_provider().complete(_system(db), prompt, json_mode=True))
    d = ReplyDecision(
        intent=str(data.get("intent", "other")), reply=str(data.get("reply", "")).strip(),
        confidence=float(data.get("confidence", 0)), needs_human=bool(data.get("needs_human", False)),
        reason=str(data.get("reason", "")),
    )
    # Code-level guardrails (uncertainty detection + human escalation)
    threshold = float(get_setting(db, "confidence_threshold"))
    if SENSITIVE.search(inbound_text):
        d.needs_human, d.reason = True, "sensitive topic detected"
    elif d.confidence < threshold:
        d.needs_human, d.reason = True, f"low confidence ({d.confidence:.2f} < {threshold})"
    elif not d.reply:
        d.needs_human, d.reason = True, d.reason or "empty reply"
    elif FORBIDDEN_OUTPUT.search(d.reply):
        d.needs_human, d.reason = True, "draft contained a decision statement"
    return d
