"""P1/T03: shared EvalExperiment claim, lease heartbeat and stale recovery (SQLite)."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from core import eval_runner
from core.eval_claim import EvalClaimConflictError, begin_claim, new_claim_owner
from core.eval_dataset_service import create_dataset
from core.eval_experiment_service import create_experiment, run_experiment
from core.models import EvalCase, EvalRun, ProjectContext, TargetDeployment
from core.session_service import SessionService
from core.target_testing import TargetTestResponse
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.errors import EvalClaimLostError

_TENANT = "claim-tenant"
_ENDPOINT = "http://target.local/eval"
_CALLS = [0]


class FakeAdapter:
    def __init__(self, config):
        self.config = config

    def execute(self, *args, **kwargs):
        _CALLS[0] += 1
        return TargetTestResponse(
            outcome="success",
            output="answer with citation",
            status_code=200,
            endpoint=_ENDPOINT,
        )


def _build_store(tmp_path) -> SQLiteSessionStore:
    store = SQLiteSessionStore(str(tmp_path / "claim.db"))
    store.initialize()
    return store


@contextmanager
def _service(tmp_path):
    store = _build_store(tmp_path)
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store


def _seed(ctx: ProjectContext):
    ctx.data_classification = "business_internal"
    ctx.target_deployment = TargetDeployment(endpoint=_ENDPOINT, version="v1")
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
        ctx, name="claim dataset", case_ids=[case.eval_id for case in ctx.eval_cases]
    )
    return create_experiment(
        ctx,
        dataset_id=dataset.dataset_id,
        name="claim experiment",
        run_mode="target_http",
        run_config={
            "target_config": {
                "endpoint": _ENDPOINT,
                "timeout_seconds": 5,
                "output_field": "output",
            }
        },
    )


def _claim(store, session_id, experiment_id, tenant=_TENANT, owner=None, key="req-key"):
    owner = owner or new_claim_owner()
    return store.claim_eval_experiment(
        session_id,
        tenant,
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


def _experiment_row(store, experiment_id):
    with store._get_conn() as conn:
        return conn.execute(
            "SELECT status, claim_owner, claim_attempt, claim_request_key, claim_lease_until "
            "FROM eval_experiments WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()


def test_concurrent_claims_only_one_wins(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def attempt() -> None:
        worker_store = SQLiteSessionStore(str(tmp_path / "claim.db"))
        barrier.wait()
        outcome = _claim(worker_store, ctx.session_id, experiment.experiment_id, key="same")
        with lock:
            results.append(outcome.reason)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert sorted(results) == ["already_running", "claimed"]
    row = _experiment_row(store, experiment.experiment_id)
    assert row["status"] == "running"
    assert int(row["claim_attempt"] or 0) == 1


def test_duplicate_request_key_does_not_reexecute(tmp_path, monkeypatch):
    _CALLS[0] = 0
    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-1",
            tenant_id=_TENANT,
        )
        assert _CALLS[0] == 2

        replay = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-1",
            tenant_id=_TENANT,
        )
        assert replay["status"] == "completed"
        assert _CALLS[0] == 2


def test_different_request_key_conflicts_while_running(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)
    first = _claim(store, ctx.session_id, experiment.experiment_id, key="req-a")
    assert first.claimed

    second = _claim(store, ctx.session_id, experiment.experiment_id, key="req-b")
    assert second.claimed is False
    assert second.reason == "request_key_mismatch"
    assert _experiment_row(store, experiment.experiment_id)["claim_attempt"] == 1


def test_attempt_is_monotonic_and_projection_keeps_claim_columns(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    experiment.execution_attempt = 3
    store.create(ctx)

    outcome = _claim(store, ctx.session_id, experiment.experiment_id, key="req-1")
    assert outcome.claim is not None
    assert outcome.claim.attempt == 4

    loaded = store.load(ctx.session_id, _TENANT)
    assert loaded is not None
    # 普通 save 的投影同步不得覆盖协调列。
    store.save(loaded)
    row = _experiment_row(store, experiment.experiment_id)
    assert row["claim_owner"] == outcome.claim.owner
    assert int(row["claim_attempt"] or 0) == 4


def test_heartbeat_requires_owner_attempt_and_live_lease(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)
    claim = _claim(store, ctx.session_id, experiment.experiment_id).claim
    assert claim is not None

    assert store.heartbeat_eval_experiment(
        ctx.session_id, _TENANT, experiment.experiment_id, claim.owner, claim.attempt, 180
    )
    assert not store.heartbeat_eval_experiment(
        ctx.session_id, _TENANT, experiment.experiment_id, "other-owner", claim.attempt, 180
    )
    assert not store.heartbeat_eval_experiment(
        ctx.session_id, _TENANT, experiment.experiment_id, claim.owner, claim.attempt + 1, 180
    )
    assert store.verify_eval_experiment_owner(
        ctx.session_id, _TENANT, experiment.experiment_id, claim.owner, claim.attempt
    )

    with store._get_conn() as conn:
        conn.execute(
            "UPDATE eval_experiments SET claim_lease_until=? WHERE experiment_id=?",
            ((datetime.utcnow() - timedelta(seconds=5)).isoformat(), experiment.experiment_id),
        )
        conn.commit()
    assert not store.verify_eval_experiment_owner(
        ctx.session_id, _TENANT, experiment.experiment_id, claim.owner, claim.attempt
    )


def test_expired_lease_recovers_and_next_claim_attempt_increments(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)
    first = _claim(store, ctx.session_id, experiment.experiment_id, key="req-1").claim
    assert first is not None

    with store._get_conn() as conn:
        conn.execute(
            "UPDATE eval_experiments SET claim_lease_until=? WHERE experiment_id=?",
            ((datetime.utcnow() - timedelta(seconds=5)).isoformat(), experiment.experiment_id),
        )
        conn.commit()

    assert store.recover_stale_eval_experiment(ctx.session_id, _TENANT, experiment.experiment_id)
    recovered = store.load(ctx.session_id, _TENANT)
    assert recovered is not None
    exp = next(
        item
        for item in recovered.eval_experiments
        if item.experiment_id == experiment.experiment_id
    )
    assert exp.status == "interrupted"
    assert exp.last_error_code == "lease_expired"
    row = _experiment_row(store, experiment.experiment_id)
    assert row["claim_owner"] is None

    second = _claim(store, ctx.session_id, experiment.experiment_id, key="req-1")
    assert second.claimed
    assert second.claim is not None
    assert second.claim.attempt == 2


def test_old_owner_progress_cannot_overwrite_new_claim(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)
    first = _claim(store, ctx.session_id, experiment.experiment_id, key="req-1")
    assert first.claim is not None

    with store._get_conn() as conn:
        conn.execute(
            "UPDATE eval_experiments SET claim_lease_until=? WHERE experiment_id=?",
            ((datetime.utcnow() - timedelta(seconds=5)).isoformat(), experiment.experiment_id),
        )
        conn.commit()
    assert store.recover_stale_eval_experiment(ctx.session_id, _TENANT, experiment.experiment_id)
    second = _claim(store, ctx.session_id, experiment.experiment_id, key="req-1")
    assert second.claim is not None

    stale_ctx = store.load(ctx.session_id, _TENANT)
    assert stale_ctx is not None
    with pytest.raises(EvalClaimLostError):
        store.save_eval_experiment_progress(
            stale_ctx,
            experiment.experiment_id,
            first.claim.owner,
            first.claim.attempt,
            terminal=True,
        )
    # 新领取的协调列保持不变。
    row = _experiment_row(store, experiment.experiment_id)
    assert row["claim_owner"] == second.claim.owner
    assert int(row["claim_attempt"] or 0) == second.claim.attempt


def test_submit_failure_releases_claim(tmp_path):
    store = _build_store(tmp_path)
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
        patch(
            "core.services.evaluation.submit_eval_experiment",
            side_effect=RuntimeError("executor down"),
        ),
    ):
        svc = SessionService()
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        with pytest.raises(RuntimeError, match="executor down"):
            svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=True,
                idempotency_key="req-bg",
                tenant_id=_TENANT,
            )

    row = _experiment_row(store, experiment.experiment_id)
    assert row["status"] == "interrupted"
    assert row["claim_owner"] is None


def test_running_experiment_different_key_raises_conflict(tmp_path):
    store = _build_store(tmp_path)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", MemoryCache(ttl_seconds=3600)),
    ):
        svc = SessionService()
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)
        _claim(store, ctx.session_id, experiment.experiment_id, key="req-a")

        with pytest.raises(EvalClaimConflictError, match="already running"):
            svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=False,
                idempotency_key="req-b",
                tenant_id=_TENANT,
            )


def _claim_with_mode(store, session_id: str, experiment_id: str, *, dry_run_only: bool, key: str):
    owner = new_claim_owner()
    return store.claim_eval_experiment(
        session_id,
        _TENANT,
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
            dry_run_only=dry_run_only,
        ),
    )


def test_claim_records_and_enforces_execution_mode(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    store.create(ctx)

    first = _claim_with_mode(
        store,
        ctx.session_id,
        experiment.experiment_id,
        dry_run_only=False,
        key="req-mode",
    )
    assert first.claimed is True
    loaded = store.load(ctx.session_id, _TENANT)
    assert loaded is not None
    stored = next(
        item for item in loaded.eval_experiments if item.experiment_id == experiment.experiment_id
    )
    assert stored.execution_mode == "target_http"

    stored.status = "interrupted"
    store.save(loaded)

    mismatch = _claim_with_mode(
        store,
        ctx.session_id,
        experiment.experiment_id,
        dry_run_only=True,
        key="req-mode",
    )
    assert mismatch.claimed is False
    assert mismatch.reason == "execution_mode_mismatch"

    resumed = _claim_with_mode(
        store,
        ctx.session_id,
        experiment.experiment_id,
        dry_run_only=False,
        key="req-mode",
    )
    assert resumed.claimed is True


def test_claim_infers_mode_from_existing_runs(tmp_path):
    store = _build_store(tmp_path)
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    ctx.eval_runs.append(
        EvalRun(
            session_id=ctx.session_id,
            eval_id=ctx.eval_cases[0].eval_id,
            experiment_id=experiment.experiment_id,
            run_mode="target_http",
            input_payload="question",
            expected_behavior="answer",
            status="failed",
        )
    )
    store.create(ctx)

    outcome = _claim_with_mode(
        store,
        ctx.session_id,
        experiment.experiment_id,
        dry_run_only=True,
        key="req-infer",
    )
    assert outcome.claimed is False
    assert outcome.reason == "execution_mode_mismatch"


def test_sync_run_rejects_mode_change(tmp_path):
    ctx = ProjectContext(tenant_id=_TENANT)
    experiment = _seed(ctx)
    experiment.status = "interrupted"
    experiment.execution_mode = "target_http"

    with pytest.raises(ValueError, match="different mode"):
        run_experiment(ctx, experiment_id=experiment.experiment_id, dry_run_only=True)


def test_status_exposes_execution_mode_and_resume_flags(tmp_path):
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        experiment.status = "failed"
        experiment.execution_mode = "target_http"
        store.create(ctx)

        status = svc.get_eval_experiment_status(ctx.session_id, experiment.experiment_id, _TENANT)
        assert status["execution_mode"] == "target_http"
        assert status["execution_mode_inferred"] is False
        assert status["resumable"] is True
        assert status["heartbeat_stale"] is False
