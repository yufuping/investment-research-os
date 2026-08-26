"""创建 Bigfish 最小结构化投资记忆层。"""

from alembic import op
import sqlalchemy as sa


revision = "0001_bigfish_knowledge"
down_revision = None
branch_labels = None
depends_on = None


UUID = sa.Uuid()
JSON = sa.JSON()


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *timestamps(),
        sa.UniqueConstraint("ticker", name="uq_companies_ticker"),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"])

    op.create_table(
        "research_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("evidence_summary", JSON, nullable=False),
        *timestamps(),
    )

    op.create_table(
        "theses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("supersedes_thesis_id", UUID, sa.ForeignKey("theses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("supporting_evidence", JSON, nullable=False),
        sa.Column("contrary_evidence", JSON, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *timestamps(),
    )

    op.create_table(
        "assumptions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("evidence", JSON, nullable=False),
        *timestamps(),
    )

    op.create_table(
        "predictions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prediction", sa.Text(), nullable=False),
        sa.Column("prediction_date", sa.Date(), nullable=False),
        sa.Column("expected_verification_date", sa.Date(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("actual_result", sa.Text(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "valuations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("reference_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("target_return", sa.Numeric(7, 4), nullable=True),
        sa.Column("base_expected_return", sa.Numeric(7, 4), nullable=True),
        sa.Column("bear_expected_return", sa.Numeric(7, 4), nullable=True),
        sa.Column("bull_expected_return", sa.Numeric(7, 4), nullable=True),
        sa.Column("assumptions", JSON, nullable=False),
        sa.Column("scenarios", JSON, nullable=False),
        *timestamps(),
    )

    op.create_table(
        "critical_unknowns",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.String(32), nullable=False),
        sa.Column("evidence_status", sa.String(32), nullable=False, server_default="insufficient"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "watch_variables",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("current_assessment", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        *timestamps(),
        sa.UniqueConstraint("company_id", "name", name="uq_watch_variable_company_name"),
    )

    op.create_table(
        "decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("explicit_user_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("position_size", sa.Numeric(9, 4), nullable=True),
        sa.Column("target_return", sa.Numeric(7, 4), nullable=True),
        sa.Column("expected_returns", JSON, nullable=False),
        sa.Column("core_thesis", sa.Text(), nullable=False),
        sa.Column("critical_assumptions", JSON, nullable=False),
        sa.Column("major_risks", JSON, nullable=False),
        sa.Column("buy_more_conditions", JSON, nullable=False),
        sa.Column("sell_conditions", JSON, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "research_updates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("company_id", UUID, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("research_session_id", UUID, sa.ForeignKey("research_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("new_facts", JSON, nullable=False),
        sa.Column("assumption_changes", JSON, nullable=False),
        sa.Column("prediction_results", JSON, nullable=False),
        sa.Column("thesis_change", sa.Text(), nullable=True),
        sa.Column("valuation_change", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        *timestamps(),
    )

    op.create_table(
        "skill_improvements",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("evidence", JSON, nullable=False),
        sa.Column("proposed_change", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("implemented_version", sa.String(64), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )


def downgrade() -> None:
    for table in (
        "skill_improvements",
        "research_updates",
        "decisions",
        "watch_variables",
        "critical_unknowns",
        "valuations",
        "predictions",
        "assumptions",
        "theses",
        "research_sessions",
        "companies",
    ):
        op.drop_table(table)
