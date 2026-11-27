import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import hash_password
from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import AdminUser, FollowUpRule, KnowledgeArticle
from .routers import core, webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

@asynccontextmanager
async def lifespan(_app):
    bootstrap()
    yield


app = FastAPI(title="HireFlow AI", version="1.0.0", lifespan=lifespan,
              description="Self-hosted AI recruitment & communications platform")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(core.router)
app.include_router(webhooks.router)


def bootstrap() -> None:
    """Create tables (dev/test; production uses Alembic) and seed first admin + starter content."""
    Base.metadata.create_all(engine)
    s = get_settings()
    db = SessionLocal()
    try:
        if not db.query(AdminUser).first():
            db.add(AdminUser(email=s.admin_email.lower(), password_hash=hash_password(s.admin_password),
                             full_name="Administrator"))
        if not db.query(KnowledgeArticle).first():
            db.add_all([
                KnowledgeArticle(title="Application process", tags="process timeline review status",
                                 content="After applying, our team reviews every application within 5 business "
                                         "days. Shortlisted applicants are contacted by email for an interview."),
                KnowledgeArticle(title="Documents", tags="cv resume documents upload",
                                 content="Applicants may send an updated CV by replying to any email from us. "
                                         "Accepted formats: PDF or DOCX."),
                KnowledgeArticle(title="Contact", tags="contact phone office hours",
                                 content="Recruitment office hours are Sunday–Thursday, 9:00–17:00 GST."),
            ])
        if not db.query(FollowUpRule).first():
            db.add(FollowUpRule(name="Nudge after 3 days of silence", trigger_status="in_review", wait_hours=72,
                                template="Hi {first_name},\n\nJust checking in — is there anything you'd like "
                                         "to add to your application with {company}? Simply reply to this email."
                                         "\n\nReply UNSUBSCRIBE to stop these emails.", max_sends=1))
        db.commit()
    finally:
        db.close()


