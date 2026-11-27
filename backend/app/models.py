"""ORM models. Schema is created/migrated with Alembic (see backend/migrations)."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Applicant(Base):
    __tablename__ = "applicants"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # normalised lower-case
    full_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="new")  # new|in_review|contacted|shortlisted|closed
    # Communication permissions / compliance
    consent_email: Mapped[bool] = mapped_column(Boolean, default=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    automation_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    human_takeover: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applications: Mapped[list["Application"]] = relationship(back_populates="applicant", order_by="Application.id")
    messages: Mapped[list["Message"]] = relationship(back_populates="applicant", order_by="Message.id")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_application_source_ext"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("applicants.id"), index=True)
    source: Mapped[str] = mapped_column(String(32), default="wordpress")
    external_id: Mapped[str] = mapped_column(String(128))  # WP entry id / idempotency key
    position: Mapped[str] = mapped_column(String(255), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending -> processed | needs_review | failed ; pending survives AI outages
    processing_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    processing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    classification: Mapped[str] = mapped_column(String(64), default="")
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    applicant: Mapped[Applicant] = relationship(back_populates="applications")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("applicants.id"), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # inbound|outbound
    channel: Mapped[str] = mapped_column(String(16), default="email")
    # outbound: draft -> approved -> sent | failed | blocked ; inbound: received
    status: Mapped[str] = mapped_column(String(16), default="received")
    author: Mapped[str] = mapped_column(String(32), default="applicant")  # applicant|ai|admin:<email>|system
    subject: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    email_message_id: Mapped[str | None] = mapped_column(String(512), unique=True, nullable=True)
    in_reply_to: Mapped[str] = mapped_column(String(512), default="")
    classification: Mapped[str] = mapped_column(String(64), default="")
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str] = mapped_column(String(255), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    applicant: Mapped[Applicant] = relationship(back_populates="messages")


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FollowUpRule(Base):
    __tablename__ = "follow_up_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    trigger_status: Mapped[str] = mapped_column(String(32), default="new")
    wait_hours: Mapped[int] = mapped_column(Integer, default=72)
    template: Mapped[str] = mapped_column(Text)
    max_sends: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FollowUpLog(Base):
    __tablename__ = "follow_up_log"
    __table_args__ = (UniqueConstraint("rule_id", "applicant_id", "sequence", name="uq_followup_once"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("follow_up_rules.id"))
    applicant_id: Mapped[int] = mapped_column(ForeignKey("applicants.id"))
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
