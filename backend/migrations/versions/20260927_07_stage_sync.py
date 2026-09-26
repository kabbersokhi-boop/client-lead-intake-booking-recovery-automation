"""Durable desired HighLevel opportunity stage and attempt ledger.

Revision ID: 20260927_07
Revises: 20260920_06
"""

from alembic import op
import sqlalchemy as sa

revision = "20260927_07"
down_revision = "20260920_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stage_sync_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False, unique=True),
        sa.Column("submission_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("desired_stage", sa.String(40), nullable=False),
        sa.Column("desired_rank", sa.Integer(), nullable=False),
        sa.Column("desired_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_owner", sa.String(160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("verified_remote_stage", sa.String(40)),
        sa.Column("last_error_class", sa.String(80)),
        sa.Column("last_error_message", sa.String(300)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("desired_rank IN (1, 2)", name="ck_stage_sync_rank"),
        sa.CheckConstraint("desired_version > 0", name="ck_stage_sync_version"),
    )
    for name in ("submission_id", "correlation_id", "state", "due_at", "lease_token"):
        op.create_index(f"ix_stage_sync_jobs_{name}", "stage_sync_jobs", [name])
    op.create_table(
        "stage_sync_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("stage_sync_jobs.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("desired_version", sa.Integer(), nullable=False),
        sa.Column("desired_stage", sa.String(40), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(40), nullable=False, server_default="started"),
        sa.Column("verified_remote_stage", sa.String(40)),
        sa.Column("error_class", sa.String(80)),
        sa.Column("status_code", sa.Integer()),
        sa.Column("retry_after_seconds", sa.Integer()),
        sa.UniqueConstraint("job_id", "attempt_number"),
    )
    op.create_index("ix_stage_sync_attempts_job_id", "stage_sync_attempts", ["job_id"])


def downgrade() -> None:
    op.drop_table("stage_sync_attempts")
    op.drop_table("stage_sync_jobs")
