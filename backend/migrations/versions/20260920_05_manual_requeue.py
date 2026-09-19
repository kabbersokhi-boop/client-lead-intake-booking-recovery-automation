"""authorize one manual attempt without resetting history

Revision ID: 20260920_05
Revises: 20260920_04
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_05"
down_revision = "20260920_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crm_write_jobs",
        sa.Column(
            "manual_attempt_authorized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("crm_write_jobs", "manual_attempt_authorized")
