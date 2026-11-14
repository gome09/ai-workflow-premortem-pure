"""P1/T03 PostgreSQL claim/lease verification with real connections.

Run with:
    E2E_DATABASE_URL=... STORAGE_BACKEND=postgres DATA_ENCRYPTION_KEY=... \
    PRODUCTION_SAFETY_REQUIRED=1 uv run pytest tests/test_postgres_eval_claim.py -q
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY", "")

if not _DATABASE_URL:
    message = "PostgreSQL eval-claim test requires E2E_DATABASE_URL."
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

import psycopg  # noqa: E402

from core.config import settings  # noqa: E402
from core.eval_claim import begin_claim, new_claim_owner  # noqa: E402
from core.eval_dataset_service import create_dataset  # noqa: E402
from core.eval_experiment_service import create_experiment  # noqa: E402
from core.models import EvalCase, ProjectContext  # noqa: E402
from storage.backends.postgres import PostgresSessionStore  # noqa: E402
from storage.field_security import _reset_fernet_cache  # noqa: E402
from storage.session_store import session_store  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _runtime() -> None:
    if settings.storage_backend != "postgres":
        pytest.fail("This test requires STORAGE_BACKEND=postgres", pytrace=False)
    if not _ENCRYPTION_KEY:
        pytest.fail("This test requires DATA_ENCRYPTION_KEY", pytrace=False)
    _reset_fernet_cache()
    session_store.initialize()


@pytest.fixture
def tenant_id() -> str:
    return str(session_store.create_tenant(f"claim-{uuid.uuid4().hex}")["tenant_id"])


def _seed(tenant_id: str) -> tuple[ProjectContext, str]:
    ctx = ProjectContext(tenant_id=tenant_id)
    ctx.data_classification = "business_internal"
    for index in range(2):
        ctx.eval_cases.append(
            EvalCase(
                session_id=ctx.session_id,
                stage_id=3,
                target_node_id="N-1",
                input_payload=f"question {index}",
                expected_behavior="answer with citation",
                pass_criteria=["citation"],
                passed=True,
            )
        )
    dataset = create_dataset(
        ctx, name="pg claim dataset", case_ids=[case.eval_id for case in ctx.eval_cases]
    )
    experiment = create_experiment(
        ctx, dataset_id=dataset.dataset_id, name="pg claim experiment", run_mode="manual"
    )
    session_store.create(ctx)
    return ctx, experiment.experiment_id


def _claim(store, session_id: str, tenant_id: str, experiment_id: str, *, key="req"):
    owner = new_claim_owner()
    return store.claim_eval_experiment(
        session_id,
        tenant_id,
        experiment_id,
        owner=owner,
        request_key=key,
        lease_seconds=180,
        decide=lambda ctx, coord, now: begin_claim(
            ctx,
            experiment_id,
            owner=owner,
            request_key=key,
            timeout_seconds=None,
            coordination_attempt=coord,
            now=now,
        ),
    )


def _expire_lease(experiment_id: str) -> None:
    with psycopg.connect(_DATABASE_URL) as conn:
        conn.execute(
            "UPDATE eval_experiments SET claim_lease_until = clock_timestamp() "
            "- interval '5 seconds' WHERE experiment_id = %s",
            (experiment_id,),
        )


def test_concurrent_claims_use_real_row_locks(tenant_id):
    ctx, experiment_id = _seed(tenant_id)
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        store = PostgresSessionStore()
        barrier.wait()
        outcome = _claim(store, ctx.session_id, tenant_id, experiment_id, key="same")
        with lock:
            results.append(outcome.reason)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == ["already_running", "claimed"]
    try:
        coord = session_store.get_eval_experiment_coordination(
            ctx.session_id, tenant_id, experiment_id
        )
        assert coord is not None
        assert coord.attempt == 1
    finally:
        session_store.delete(ctx.session_id, tenant_id)


def test_heartbeat_extends_lease_and_rejects_old_owner(tenant_id):
    ctx, experiment_id = _seed(tenant_id)
    try:
        outcome = _claim(session_store, ctx.session_id, tenant_id, experiment_id)
        claim = outcome.claim
        assert claim is not None
        assert session_store.heartbeat_eval_experiment(
            ctx.session_id, tenant_id, experiment_id, claim.owner, claim.attempt, 180
        )
        assert not session_store.heartbeat_eval_experiment(
            ctx.session_id, tenant_id, experiment_id, "old-owner", claim.attempt, 180
        )
        assert session_store.verify_eval_experiment_owner(
            ctx.session_id, tenant_id, experiment_id, claim.owner, claim.attempt
        )

        _expire_lease(experiment_id)
        assert not session_store.verify_eval_experiment_owner(
            ctx.session_id, tenant_id, experiment_id, claim.owner, claim.attempt
        )
    finally:
        session_store.delete(ctx.session_id, tenant_id)


def test_expired_lease_recovers_and_old_owner_cannot_write(tenant_id):
    ctx, experiment_id = _seed(tenant_id)
    try:
        first = _claim(session_store, ctx.session_id, tenant_id, experiment_id, key="req-1")
        assert first.claim is not None
        _expire_lease(experiment_id)
        assert session_store.recover_stale_eval_experiment(ctx.session_id, tenant_id, experiment_id)
        recovered = session_store.load(ctx.session_id, tenant_id)
        assert recovered is not None
        exp = next(
            item for item in recovered.eval_experiments if item.experiment_id == experiment_id
        )
        assert exp.status == "interrupted"
        assert exp.last_error_code == "lease_expired"

        second = _claim(session_store, ctx.session_id, tenant_id, experiment_id, key="req-1")
        assert second.claim is not None
        assert second.claim.attempt == 2

        stale_ctx = session_store.load(ctx.session_id, tenant_id)
        assert stale_ctx is not None
        with pytest.raises(Exception) as excinfo:
            session_store.save_eval_experiment_progress(
                stale_ctx,
                experiment_id,
                first.claim.owner,
                first.claim.attempt,
                terminal=True,
            )
        assert type(excinfo.value).__name__ == "EvalClaimLostError"
    finally:
        session_store.delete(ctx.session_id, tenant_id)


def test_coordination_read_does_not_need_context_owner_leak(tenant_id):
    ctx, experiment_id = _seed(tenant_id)
    try:
        outcome = _claim(session_store, ctx.session_id, tenant_id, experiment_id)
        coord = session_store.get_eval_experiment_coordination(
            ctx.session_id, tenant_id, experiment_id
        )
        assert coord is not None
        assert coord.attempt == outcome.claim.attempt
        assert coord.lease_until is not None
        assert coord.heartbeat_at is not None
    finally:
        session_store.delete(ctx.session_id, tenant_id)
