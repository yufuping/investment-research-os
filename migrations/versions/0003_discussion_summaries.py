"""保存经用户确认的公司讨论纪要。"""

from alembic import op
import sqlalchemy as sa


revision = "0003_discussion_summaries"
down_revision = "0002_decision_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discussion_summaries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discussion_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_points", sa.JSON(), nullable=False),
        sa.Column("changed_views", sa.JSON(), nullable=False),
        sa.Column("conclusions", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("follow_up_items", sa.JSON(), nullable=False),
        sa.Column("source_chat_reference", sa.String(512), nullable=True),
        sa.Column("related_report_id", sa.String(512), nullable=True),
        sa.Column("explicit_user_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recorded_via", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_discussion_summaries_company_id", "discussion_summaries", ["company_id"])
    op.create_index("ix_discussion_summaries_discussion_date", "discussion_summaries", ["discussion_date"])


def downgrade() -> None:
    op.drop_table("discussion_summaries")
