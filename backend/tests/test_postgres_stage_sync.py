import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from test_highlevel_adapter import lead_payload

from app.config import settings
from app.models import Lead, StageSyncJob
from app.providers.crm import DevelopmentCRMProvider
from app.services.stage_sync_service import StageSyncLeaseError, StageSyncService

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="requires disposable PostgreSQL")


@pytest.fixture(scope="module")
def sessions():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = POSTGRES_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_URL)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_postgres_claim_and_expired_writer_cannot_downgrade(sessions, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    service = StageSyncService()
    with sessions() as db:
        lead = DevelopmentCRMProvider().create_lead(db, lead_payload()).lead
        job = service.advance(db, lead, "contacted")
        db.commit()
        job_id = job.id
        lead_id = lead.id

    barrier = threading.Barrier(2)

    def claim_once(index):
        with sessions() as db:
            barrier.wait()
            claimed = service.claim(db, f"worker-{index}")
            return claimed.lease_token if claimed else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(claim_once, range(2)))
    assert sum(token is not None for token in tokens) == 1
    old_token = next(token for token in tokens if token is not None)

    entered = threading.Event()
    release = threading.Event()

    class DelayedClient:
        def sync_opportunity_stage(self, _lead, stage):
            assert stage == "contacted"
            entered.set()
            assert release.wait(10)
            return "contacted"

    def old_worker():
        with sessions() as db:
            try:
                service.process(db, job_id, old_token, DelayedClient())
            except StageSyncLeaseError:
                return "stale"
            return "unexpected_settlement"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(old_worker)
        assert entered.wait(10)
        with sessions() as db:
            lead = db.get(Lead, lead_id)
            service.advance(db, lead, "appointment_booked")
            job = db.get(StageSyncJob, job_id)
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        with sessions() as db:
            new_claim = service.claim(db, "new-worker")
            assert new_claim.lease_token != old_token
            busy = service.process(db, job_id, new_claim.lease_token, DelayedClient())
            assert busy.state == "retry_wait"
        release.set()
        assert future.result(timeout=10) == "stale"

    with sessions() as db:
        job = db.get(StageSyncJob, job_id)
        job.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        final_claim = service.claim(db, "final-worker")

        class FinalClient:
            def sync_opportunity_stage(self, _lead, stage):
                assert stage == "appointment_booked"
                return stage

        result = service.process(db, job_id, final_claim.lease_token, FinalClient())
        assert (result.state, result.desired_version, result.verified_remote_stage) == (
            "completed", 2, "appointment_booked"
        )
