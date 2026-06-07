"""add customer ticket fields

Revision ID: 20260607_0002
Revises: 20260607_0001
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20260607_0002"
down_revision = "20260607_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("customer_name", sa.String(length=120), nullable=False, server_default="Клиент"))
    op.add_column("analyses", sa.Column("channel", sa.String(length=40), nullable=False, server_default="web"))
    op.add_column("analyses", sa.Column("category", sa.String(length=40), nullable=False, server_default="other"))
    op.add_column("analyses", sa.Column("urgency", sa.String(length=24), nullable=False, server_default="normal"))
    op.add_column("analyses", sa.Column("suggested_reply", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("analyses", "suggested_reply")
    op.drop_column("analyses", "urgency")
    op.drop_column("analyses", "category")
    op.drop_column("analyses", "channel")
    op.drop_column("analyses", "customer_name")
