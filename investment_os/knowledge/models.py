from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class KnowledgeBase(DeclarativeBase):
    """与 Legacy SQLite Base 隔离，避免迁移期间互相创建表。"""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Company(TimestampMixin, KnowledgeBase):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class ResearchSession(TimestampMixin, KnowledgeBase):
    __tablename__ = "research_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    objective: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="completed")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Thesis(TimestampMixin, KnowledgeBase):
    __tablename__ = "theses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    supersedes_thesis_id: Mapped[UUID | None] = mapped_column(ForeignKey("theses.id", ondelete="SET NULL"), nullable=True)
    thesis: Mapped[str] = mapped_column(Text)
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    contrary_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class Assumption(TimestampMixin, KnowledgeBase):
    __tablename__ = "assumptions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class Prediction(TimestampMixin, KnowledgeBase):
    __tablename__ = "predictions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    prediction: Mapped[str] = mapped_column(Text)
    prediction_date: Mapped[date] = mapped_column(Date, default=date.today)
    expected_verification_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    actual_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="pending")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Valuation(TimestampMixin, KnowledgeBase):
    __tablename__ = "valuations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    valuation_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    target_return: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    base_expected_return: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    bear_expected_return: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    bull_expected_return: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    scenarios: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class CriticalUnknown(TimestampMixin, KnowledgeBase):
    __tablename__ = "critical_unknowns"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(32))
    evidence_status: Mapped[str] = mapped_column(String(32), default="insufficient")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WatchVariable(TimestampMixin, KnowledgeBase):
    __tablename__ = "watch_variables"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_watch_variable_company_name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    rationale: Mapped[str] = mapped_column(Text)
    current_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Decision(TimestampMixin, KnowledgeBase):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    decision_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    action: Mapped[str] = mapped_column(String(32))
    explicit_user_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position_size: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    target_return: Mapped[Decimal | None] = mapped_column(Numeric(7, 4), nullable=True)
    decision_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_returns: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    core_thesis: Mapped[str] = mapped_column(Text)
    critical_assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)
    major_risks: Mapped[list[str]] = mapped_column(JSON, default=list)
    buy_more_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    sell_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_via: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DiscussionSummary(TimestampMixin, KnowledgeBase):
    """由 ChatGPT 提炼、用户确认后保存的公司讨论纪要。"""

    __tablename__ = "discussion_summaries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    discussion_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    changed_views: Mapped[list[str]] = mapped_column(JSON, default=list)
    conclusions: Mapped[list[str]] = mapped_column(JSON, default=list)
    unresolved_questions: Mapped[list[str]] = mapped_column(JSON, default=list)
    follow_up_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_chat_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    related_report_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    explicit_user_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recorded_via: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SavedResearchReport(TimestampMixin, KnowledgeBase):
    __tablename__ = "saved_research_reports"
    __table_args__ = (UniqueConstraint("company_id", "version", name="uq_saved_report_company_version"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    previous_report_id: Mapped[UUID | None] = mapped_column(ForeignKey("saved_research_reports.id", ondelete="SET NULL"), nullable=True)
    version: Mapped[int] = mapped_column()
    report_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    change_summary: Mapped[list[str]] = mapped_column(JSON, default=list)
    explicit_user_confirmation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    generated_by: Mapped[str] = mapped_column(String(64), default="chatgpt_frontend")
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SavedResearchReportSection(TimestampMixin, KnowledgeBase):
    __tablename__ = "saved_research_report_sections"
    __table_args__ = (UniqueConstraint("report_id", "section_order", name="uq_saved_report_section_order"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    report_id: Mapped[UUID] = mapped_column(ForeignKey("saved_research_reports.id", ondelete="CASCADE"), index=True)
    section_order: Mapped[int] = mapped_column()
    heading: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)


class ResearchUpdate(TimestampMixin, KnowledgeBase):
    __tablename__ = "research_updates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    research_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True)
    new_facts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    assumption_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    prediction_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    thesis_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    valuation_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text)


class SkillImprovement(TimestampMixin, KnowledgeBase):
    __tablename__ = "skill_improvements"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(64), index=True)
    problem: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    proposed_change: Mapped[str] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    implemented_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
