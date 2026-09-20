"""bind recovery attempts and quota permits to their owning lease

Revision ID: 20260920_06
Revises: 20260920_05
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_06"
down_revision = "20260920_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crm_write_jobs",
        sa.Column(
            "reconciliation_failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "crm_write_jobs",
        sa.Column("quota_permit_lease_token", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "crm_write_attempts",
        sa.Column("lease_token", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_crm_write_attempts_lease_token",
        "crm_write_attempts",
        ["lease_token"],
    )
    op.create_check_constraint(
        "ck_crm_job_reconciliation_failures",
        "crm_write_jobs",
        "reconciliation_failure_count >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_crm_job_reconciliation_failures",
        "crm_write_jobs",
        type_="check",
    )
    op.drop_index("ix_crm_write_attempts_lease_token", table_name="crm_write_attempts")
    op.drop_column("crm_write_attempts", "lease_token")
    op.drop_column("crm_write_jobs", "quota_permit_lease_token")
    op.drop_column("crm_write_jobs", "reconciliation_failure_count")
