import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from test_leads import payload

from app.api.routes import _apply_fault_quota
from app.models import CRMFaultRun
from app.schemas.lead import CRMLeadCreate
from app.services.recovery_service import RecoveryService

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL is not configured")


@pytest.fixture(scope="module")
def postgres_sessions():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = POSTGRES_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_URL)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield sessions
    engine.dispose()


def test_overlapping_workers_share_one_fixed_window_quota(postgres_sessions):
    submissions = [uuid.uuid4() for _ in range(10)]
    correlations = [uuid.uuid4() for _ in range(10)]
    run_id = uuid.uuid4()
    with postgres_sessions() as db:
        for submission_id, correlation_id in zip(submissions, correlations, strict=True):
            request = CRMLeadCreate.model_validate(
                payload(
                    submission_id=str(submission_id), correlation_id=str(correlation_id)
                )
            )
            RecoveryService().admit(db, request)
        db.add(
            CRMFaultRun(
                run_id=run_id,
                submission_ids=[str(value) for value in submissions],
                active=True,
                hold_delivery=False,
                request_limit=5,
                window_seconds=10,
            )
        )
        db.commit()

    barrier = threading.Barrier(len(submissions))

    def request_permission(index):
        with postgres_sessions() as db:
            barrier.wait()
            try:
                _apply_fault_quota(db, submissions[index], f"overlap-{index}")
                return 200
            except HTTPException as error:
                return error.status_code

    with ThreadPoolExecutor(max_workers=len(submissions)) as executor:
        statuses = list(executor.map(request_permission, range(len(submissions))))

    assert statuses.count(200) == 5
    assert statuses.count(429) == 5
    with postgres_sessions() as db:
        run = db.scalar(select(CRMFaultRun).where(CRMFaultRun.run_id == run_id))
        assert run.window_count == 5
