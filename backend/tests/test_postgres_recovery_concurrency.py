import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from test_leads import payload

from app.api.routes import _apply_fault_quota, recovery_quota_permission
from app.models import CRMFaultRun, CRMWriteJob
from app.schemas.lead import CRMLeadCreate
from app.schemas.recovery import QuotaPermissionRequest
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
                _apply_fault_quota(db, submissions[index])
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


def test_workers_claim_distinct_jobs_without_locking_the_backlog(postgres_sessions):
    submissions = [uuid.uuid4() for _ in range(4)]
    with postgres_sessions() as db:
        for submission_id in submissions:
            RecoveryService().admit(
                db,
                CRMLeadCreate.model_validate(
                    payload(
                        submission_id=str(submission_id), correlation_id=str(uuid.uuid4())
                    )
                ),
            )

    barrier = threading.Barrier(4)

    def claim(index):
        with postgres_sessions() as db:
            barrier.wait()
            job = RecoveryService().claim(db, f"worker-{index}")
            return job.id

    with ThreadPoolExecutor(max_workers=4) as executor:
        claimed = list(executor.map(claim, range(4)))
    assert len(set(claimed)) == 4


def test_quota_permission_and_direct_write_path_use_one_lock_order(postgres_sessions):
    permission_submission = uuid.uuid4()
    direct_submission = uuid.uuid4()
    run_id = uuid.uuid4()
    with postgres_sessions() as db:
        for submission_id in [permission_submission, direct_submission]:
            RecoveryService().admit(
                db,
                CRMLeadCreate.model_validate(
                    payload(
                        submission_id=str(submission_id), correlation_id=str(uuid.uuid4())
                    )
                ),
            )
        db.add(
            CRMFaultRun(
                run_id=run_id,
                submission_ids=[str(permission_submission), str(direct_submission)],
                active=True,
                hold_delivery=False,
                request_limit=5,
                window_seconds=10,
            )
        )
        db.commit()
        permission_job = db.scalar(
            select(CRMWriteJob).where(CRMWriteJob.submission_id == permission_submission)
        )
        claimed = RecoveryService().claim_specific(
            db, permission_job.id, "permission-worker"
        )
        permission_job_id = claimed.id
        permission_token = claimed.lease_token

    barrier = threading.Barrier(2)

    def permission_path():
        with postgres_sessions() as db:
            barrier.wait()
            result = recovery_quota_permission(
                permission_job_id,
                QuotaPermissionRequest(lease_token=permission_token),
                None,
                db,
            )
            return result["granted"]

    def direct_path():
        with postgres_sessions() as db:
            barrier.wait()
            _apply_fault_quota(db, direct_submission)
            return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda call: call(), [permission_path, direct_path]))
    assert results == [True, True]
    with postgres_sessions() as db:
        run = db.get(CRMFaultRun, run_id)
        assert run.window_count == 2


def test_stale_quota_permit_is_bound_to_original_lease(postgres_sessions):
    submission_id = uuid.uuid4()
    with postgres_sessions() as db:
        job, _ = RecoveryService().admit(
            db,
            CRMLeadCreate.model_validate(
                payload(submission_id=str(submission_id), correlation_id=str(uuid.uuid4()))
            ),
        )
        db.add(
            CRMFaultRun(
                run_id=uuid.uuid4(),
                submission_ids=[str(submission_id)],
                active=True,
                hold_delivery=False,
                request_limit=5,
                window_seconds=120,
            )
        )
        db.commit()
        first = RecoveryService().claim_specific(db, job.id, "first")
        first_token = first.lease_token
        assert recovery_quota_permission(
            job.id,
            QuotaPermissionRequest(lease_token=first_token),
            None,
            db,
        )["granted"]
        first.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    with postgres_sessions() as db:
        second = RecoveryService().claim_specific(db, job.id, "second")
        assert second.lease_token != first_token
        with pytest.raises(HTTPException) as caught:
            _apply_fault_quota(db, submission_id, first_token)
        assert caught.value.status_code == 409
        db.rollback()
        current = db.get(CRMWriteJob, second.id)
        assert current.quota_permit_until is None
        assert current.quota_permit_lease_token is None
