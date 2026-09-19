"""preserve source timestamps and make submission replays safe

Revision ID: 20260919_02
Revises: 20260919_01
Create Date: 2026-09-19
"""

import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "20260919_02"
down_revision = "20260919_01"
branch_labels = None
depends_on = None


def _fingerprint(row: dict) -> str:
    normalized = {
        "full_name": row["full_name"].strip().casefold(),
        "email": row["email"].strip().casefold() if row["email"] else None,
        "phone": "".join(character for character in (row["phone"] or "") if character.isdigit())
        or None,
        "normalized_message": row["original_message"].strip(),
    }
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def upgrade() -> None:
    op.add_column("leads", sa.Column("normalized_message", sa.Text(), nullable=True))
    op.add_column("leads", sa.Column("submission_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("leads", sa.Column("client_received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("provider_metadata", sa.JSON(), nullable=True))

    bind = op.get_bind()
    leads = sa.table(
        "leads",
        sa.column("id"),
        sa.column("full_name"),
        sa.column("email"),
        sa.column("phone"),
        sa.column("original_message"),
        sa.column("created_at"),
        sa.column("normalized_message"),
        sa.column("submission_fingerprint"),
        sa.column("client_received_at"),
    )
    rows = bind.execute(
        sa.select(
            leads.c.id,
            leads.c.full_name,
            leads.c.email,
            leads.c.phone,
            leads.c.original_message,
            leads.c.created_at,
        )
    ).mappings()
    for row in rows:
        bind.execute(
            leads.update()
            .where(leads.c.id == row["id"])
            .values(
                normalized_message=row["original_message"].strip(),
                submission_fingerprint=_fingerprint(row),
                client_received_at=row["created_at"],
            )
        )

    with op.batch_alter_table("leads") as batch:
        batch.alter_column("normalized_message", existing_type=sa.Text(), nullable=False)
        batch.alter_column(
            "submission_fingerprint", existing_type=sa.String(length=64), nullable=False
        )
        batch.alter_column(
            "client_received_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        batch.drop_column("provider_metadata")
        batch.drop_column("client_received_at")
        batch.drop_column("submission_fingerprint")
        batch.drop_column("normalized_message")
