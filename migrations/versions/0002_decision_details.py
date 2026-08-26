"""扩展真实投资决策的成交细节与审计字段。"""

from alembic import op
import sqlalchemy as sa


revision = "0002_decision_details"
down_revision = "0001_bigfish_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("decisions", sa.Column("currency", sa.String(8), nullable=True))
    op.add_column("decisions", sa.Column("quantity", sa.Numeric(20, 6), nullable=True))
    op.add_column("decisions", sa.Column("quantity_unit", sa.String(32), nullable=True))
    op.add_column("decisions", sa.Column("decision_type", sa.String(64), nullable=True))
    op.add_column("decisions", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("decisions", sa.Column("recorded_via", sa.String(64), nullable=True))


def downgrade() -> None:
    for column in ("recorded_via", "notes", "decision_type", "quantity_unit", "quantity", "currency"):
        op.drop_column("decisions", column)
