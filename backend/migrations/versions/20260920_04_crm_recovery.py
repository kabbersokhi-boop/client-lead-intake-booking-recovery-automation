"""add durable CRM write recovery

Revision ID: 20260920_04
Revises: 20260920_03
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_04"
down_revision = "20260920_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_fault_runs",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("submission_ids", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("hold_delivery", sa.Boolean(), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True)),
        sa.Column("window_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("request_limit > 0 AND window_seconds > 0", name="ck_fault_quota_positive"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "crm_write_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("operation_kind", sa.String(40), nullable=False),
        sa.Column("payload_fingerprint", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_owner", sa.String(160)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("quota_permit_until", sa.DateTime(timezone=True)),
        sa.Column("completed_lead_id", sa.Uuid()),
        sa.Column("last_error_class", sa.String(80)),
        sa.Column("last_error_message", sa.String(300)),
        sa.Column("source_execution_reference", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("state IN ('pending','processing','retry_wait','completed','needs_review','blocked')", name="ck_crm_job_state"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_crm_job_attempts"),
        sa.ForeignKeyConstraint(["completed_lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "operation_kind"),
    )
    for column in ["submission_id", "correlation_id", "state", "due_at", "lease_token", "lease_expires_at"]:
        op.create_index(f"ix_crm_write_jobs_{column}", "crm_write_jobs", [column])
    op.create_table(
        "crm_write_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("error_class", sa.String(80)),
        sa.Column("retry_after_raw", sa.String(160)),
        sa.Column("retry_after_seconds", sa.Integer()),
        sa.Column("execution_reference", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["crm_write_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number"),
    )
    op.create_index("ix_crm_write_attempts_job_id", "crm_write_attempts", ["job_id"])
    op.create_table(
        "recovery_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(200), nullable=False),
        sa.Column("job_id", sa.Uuid()),
        sa.Column("correlation_id", sa.Uuid()),
        sa.Column("workflow_reference", sa.String(160)),
        sa.Column("execution_reference", sa.String(160)),
        sa.Column("failed_node", sa.String(160)),
        sa.Column("error_class", sa.String(80), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["job_id"], ["crm_write_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index("ix_recovery_incidents_job_id", "recovery_incidents", ["job_id"])
    op.create_index("ix_recovery_incidents_correlation_id", "recovery_incidents", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("recovery_incidents")
    op.drop_table("crm_write_attempts")
    op.drop_table("crm_write_jobs")
    op.drop_table("crm_fault_runs")
