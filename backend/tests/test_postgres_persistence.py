import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from test_leads import payload

from app.models import AuditEvent, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import CRMLeadCreate

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="requires disposable PostgreSQL")


def migrate_postgres() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = POSTGRES_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_postgres_migration_persistence_and_concurrent_replay():
    migrate_postgres()
    engine = create_engine(POSTGRES_URL)
    assert {"normalized_message", "submission_fingerprint", "client_received_at"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("leads")}
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    request = CRMLeadCreate.model_validate(payload())

    def create_once():
        session = session_factory()
        try:
            return DevelopmentCRMProvider().create_lead(session, request)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create_once(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert results[0].lead.id == results[1].lead.id
    with session_factory() as session:
        lead = session.scalar(select(Lead).where(Lead.submission_id == request.submission_id))
        audits = list(session.scalars(select(AuditEvent).where(AuditEvent.lead_id == lead.id)))
        assert lead is not None
        assert lead.client_received_at == request.received_at
        assert lead.created_at is not None
        assert len(audits) == 1
        assert audits[0].metadata_json["client_received_at"] == request.received_at.isoformat()
        assert audits[0].metadata_json["persisted_at"]
