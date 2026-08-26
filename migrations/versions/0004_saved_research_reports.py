"""保存由前端 ChatGPT 生成的分段研报及版本。"""

from alembic import op
import sqlalchemy as sa


revision = "0004_saved_research_reports"
down_revision = "0003_discussion_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_research_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_report_id", sa.Uuid(), sa.ForeignKey("saved_research_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("change_summary", sa.JSON(), nullable=False),
        sa.Column("explicit_user_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generated_by", sa.String(64), nullable=False, server_default="chatgpt_frontend"),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "version", name="uq_saved_report_company_version"),
    )
    op.create_index("ix_saved_research_reports_company_id", "saved_research_reports", ["company_id"])
    op.create_index("ix_saved_research_reports_report_date", "saved_research_reports", ["report_date"])
    op.create_index("ix_saved_research_reports_status", "saved_research_reports", ["status"])
    op.create_table(
        "saved_research_report_sections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("report_id", sa.Uuid(), sa.ForeignKey("saved_research_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section_order", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("report_id", "section_order", name="uq_saved_report_section_order"),
    )
    op.create_index("ix_saved_research_report_sections_report_id", "saved_research_report_sections", ["report_id"])


def downgrade() -> None:
    op.drop_table("saved_research_report_sections")
    op.drop_table("saved_research_reports")
