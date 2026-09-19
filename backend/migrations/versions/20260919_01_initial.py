"""initial development CRM schema

Revision ID: 20260919_01
Revises:
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "20260919_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=254)),
        sa.Column("phone", sa.String(length=50)),
        sa.Column("original_message", sa.Text(), nullable=False),
        sa.Column("service_type", sa.String(length=80)),
        sa.Column("location", sa.String(length=160)),
        sa.Column("preferred_time", sa.String(length=160)),
        sa.Column("urgency", sa.String(length=20)),
        sa.Column("summary", sa.Text()),
        sa.Column("ai_status", sa.String(length=30), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("pipeline_stage", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("submission_id"),
    )
    op.create_index("ix_leads_submission_id", "leads", ["submission_id"])
    op.create_index("ix_leads_correlation_id", "leads", ["correlation_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]), sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_lead_id", "audit_events", ["lead_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("leads")
