"""add follow-up and appointment lifecycle

Revision ID: 20260920_03
Revises: 20260919_02
Create Date: 2026-09-20
"""

from alembic import op
import sqlalchemy as sa

revision = "20260920_03"
down_revision = "20260919_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('pending', 'sent', 'cancelled')", name="ck_follow_up_status"),
        sa.CheckConstraint(
            "(status = 'pending' AND sent_at IS NULL AND cancelled_at IS NULL) OR "
            "(status = 'sent' AND sent_at IS NOT NULL AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND sent_at IS NULL AND cancelled_at IS NOT NULL)",
            name="ck_follow_up_timestamps",
        ),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id"),
    )
    op.create_index("ix_follow_ups_lead_id", "follow_ups", ["lead_id"])
    op.create_index("ix_follow_ups_correlation_id", "follow_ups", ["correlation_id"])
    op.create_index("ix_follow_ups_due_at", "follow_ups", ["due_at"])

    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_request_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("business_timezone", sa.String(length=80), nullable=False),
        sa.Column("booking_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("confirmation_sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("status = 'booked'", name="ck_appointment_status"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("booking_request_id"),
        sa.UniqueConstraint("lead_id"),
    )
    op.create_index("ix_appointments_booking_request_id", "appointments", ["booking_request_id"])
    op.create_index("ix_appointments_lead_id", "appointments", ["lead_id"])
    op.create_index("ix_appointments_correlation_id", "appointments", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("appointments")
    op.drop_table("follow_ups")
