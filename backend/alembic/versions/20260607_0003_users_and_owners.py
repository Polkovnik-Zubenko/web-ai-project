"""add users and ticket owners

Revision ID: 20260607_0003
Revises: 20260607_0002
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20260607_0003"
down_revision = "20260607_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="manager"),
        sa.Column("company", sa.String(length=120), nullable=False, server_default="Northwind Retail"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.add_column("analyses", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_analyses_owner_id_users", "analyses", "users", ["owner_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_analyses_owner_id_users", "analyses", type_="foreignkey")
    op.drop_column("analyses", "owner_id")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
