# tests/test_eval_batch_resilience.py
"""Long EvalExperiment batches: per-item persistence, idempotency, timeout, resume."""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from core import eval_runner
from core.eval_dataset_service import create_dataset
from core.eval_experiment_service import EvalExperimentTimeoutError, create_experiment
from core.models import EvalCase, ProjectContext, TargetDeployment
from core.session_service import SessionService
from core.target_testing import TargetTestResponse
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore

_TENANT = "eval-batch-tenant"
_ENDPOINT = "http://target.local/eval"
_EXPECTED_CALLS = [0]


class FakeAdapter:
    def __init__(self, config):
        self.config = config

    def execute(self, *args, **kwargs):
        _EXPECTED_CALLS[0] += 1
        return TargetTestResponse(
            outcome="success",
            output="answer with citation",
            status_code=200,
            endpoint=_ENDPOINT,
        )


class SlowAdapter(FakeAdapter):
    def __init__(self, config, delay: float = 0.8):
        super().__init__(config)
        self.delay = delay

    def execute(self, *args, **kwargs):
        time.sleep(self.delay)
        return super().execute(*args, **kwargs)


class ScheduledAdapter:
    """First case fails, second case outlives the deadline, third is never started."""

    def __init__(self, config):
        self.config = config

    def execute(self, *args, **kwargs):
        index = _EXPECTED_CALLS[0]
        _EXPECTED_CALLS[0] += 1
        if index == 0:
            return TargetTestResponse(
                outcome="timeout",
                status_code=None,
                error_code="timeout",
                error_message="target timed out",
                endpoint=_ENDPOINT,
            )
        if index == 1:
            time.sleep(1.2)
        return TargetTestResponse(
            outcome="success",
            output="answer with citation",
            status_code=200,
            endpoint=_ENDPOINT,
        )


@contextmanager
def _service(tmp_path):
    store = SQLiteSessionStore(str(tmp_path / "eval_batch.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService(), store


def _seed(ctx: ProjectContext):
    ctx.data_classification = "business_internal"
    ctx.target_deployment = TargetDeployment(endpoint=_ENDPOINT, version="v1")
    for index in range(3):
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
        ctx,
        name="batch dataset",
        case_ids=[case.eval_id for case in ctx.eval_cases],
    )
    experiment = create_experiment(
        ctx,
        dataset_id=dataset.dataset_id,
        name="batch experiment",
        run_mode="target_http",
        run_config={
            "target_config": {
                "endpoint": _ENDPOINT,
                "timeout_seconds": 5,
                "output_field": "output",
            }
        },
    )
    return experiment


def test_batch_saves_per_item_and_reuses_completed_runs(tmp_path, monkeypatch):
    _EXPECTED_CALLS[0] = 0
    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        result = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-1",
            tenant_id=_TENANT,
        )
        assert result["status"] == "completed"
        assert _EXPECTED_CALLS[0] == 3

        saved = store.load(ctx.session_id, _TENANT)
        assert saved is not None
        saved_exp = next(
            item
            for item in saved.eval_experiments
            if item.experiment_id == experiment.experiment_id
        )
        assert len(saved_exp.run_ids) == 3
        assert len({run.run_id for run in saved.eval_runs}) == 3

        replay = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-1",
            tenant_id=_TENANT,
        )
        assert replay["status"] == "completed"
        assert _EXPECTED_CALLS[0] == 3


def test_timeout_preserves_completed_runs_and_resume_skips_them(tmp_path, monkeypatch):
    _EXPECTED_CALLS[0] = 0
    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", SlowAdapter)
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        with pytest.raises(EvalExperimentTimeoutError):
            svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=False,
                idempotency_key="req-timeout",
                timeout_seconds=1,
                tenant_id=_TENANT,
            )

        timed_out = store.load(ctx.session_id, _TENANT)
        assert timed_out is not None
        exp = next(
            item
            for item in timed_out.eval_experiments
            if item.experiment_id == experiment.experiment_id
        )
        assert exp.status == "failed"
        assert exp.last_error_code == "experiment_timeout"
        assert 0 < len(exp.run_ids) < 3
        completed_before = len(exp.run_ids)

        resumed = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-timeout",
            timeout_seconds=10,
            tenant_id=_TENANT,
        )
        assert resumed["status"] == "completed"
        assert _EXPECTED_CALLS[0] == 3

        final = store.load(ctx.session_id, _TENANT)
        assert final is not None
        final_exp = next(
            item
            for item in final.eval_experiments
            if item.experiment_id == experiment.experiment_id
        )
        assert len(final_exp.run_ids) == 3
        assert len(set(final_exp.run_ids)) == 3
        assert completed_before <= len(final_exp.run_ids)


def test_resume_does_not_reexecute_saved_failed_runs(tmp_path, monkeypatch):
    _EXPECTED_CALLS[0] = 0
    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", ScheduledAdapter)
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        with pytest.raises(EvalExperimentTimeoutError):
            svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=False,
                idempotency_key="req-failed",
                timeout_seconds=1,
                tenant_id=_TENANT,
            )

        timed_out = store.load(ctx.session_id, _TENANT)
        assert timed_out is not None
        exp = next(
            item
            for item in timed_out.eval_experiments
            if item.experiment_id == experiment.experiment_id
        )
        assert exp.status == "failed"
        assert len(exp.run_ids) == 2
        assert _EXPECTED_CALLS[0] == 2

        resumed = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=False,
            idempotency_key="req-failed",
            timeout_seconds=10,
            tenant_id=_TENANT,
        )
        assert resumed["status"] == "completed"
        # Case 1 was saved as failed and case 2 as completed: resume executes only case 3.
        assert _EXPECTED_CALLS[0] == 3

        final = store.load(ctx.session_id, _TENANT)
        assert final is not None
        final_exp = next(
            item
            for item in final.eval_experiments
            if item.experiment_id == experiment.experiment_id
        )
        assert len(final_exp.run_ids) == 3
        assert len(set(final_exp.run_ids)) == 3


def test_background_run_exposes_status_and_completes(tmp_path, monkeypatch):
    _EXPECTED_CALLS[0] = 0
    monkeypatch.setattr(eval_runner, "HttpJsonTargetAdapter", FakeAdapter)
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)

        accepted = svc.run_eval_experiment(
            ctx.session_id,
            experiment_id=experiment.experiment_id,
            dry_run_only=False,
            background=True,
            idempotency_key="req-bg",
            tenant_id=_TENANT,
        )
        assert accepted["accepted"] is True

        status: dict = {}
        for _ in range(100):
            status = svc.get_eval_experiment_status(
                ctx.session_id, experiment.experiment_id, _TENANT
            )
            if status["status"] in {"completed", "failed", "interrupted"}:
                break
            time.sleep(0.1)
        assert status["status"] == "completed"
        assert status["completed_cases"] == 3
        assert _EXPECTED_CALLS[0] == 3


def test_running_experiment_rejects_second_start(tmp_path):
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        experiment.status = "running"
        experiment.last_heartbeat_at = __import__("datetime").datetime.utcnow()
        store.create(ctx)

        with pytest.raises(ValueError, match="already running"):
            svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=True,
                tenant_id=_TENANT,
            )


def test_background_submission_conflicts_before_worker_marks_running(tmp_path):
    import threading

    from core.eval_execution import submit_eval_experiment

    release = threading.Event()
    with _service(tmp_path) as (svc, store):
        ctx = ProjectContext(tenant_id=_TENANT)
        experiment = _seed(ctx)
        store.create(ctx)
        exec_key = f"{ctx.session_id}:{experiment.experiment_id}"
        submit_eval_experiment(exec_key, lambda: release.wait(5), request_key="req-first")
        try:
            with pytest.raises(ValueError, match="already running"):
                svc.run_eval_experiment(
                    ctx.session_id,
                    experiment_id=experiment.experiment_id,
                    dry_run_only=False,
                    background=True,
                    idempotency_key="req-second",
                    tenant_id=_TENANT,
                )
            duplicate = svc.run_eval_experiment(
                ctx.session_id,
                experiment_id=experiment.experiment_id,
                dry_run_only=False,
                background=True,
                idempotency_key="req-first",
                tenant_id=_TENANT,
            )
            assert duplicate["accepted"] is True
        finally:
            release.set()


def test_run_and_status_routes_map_background_contract(auth_headers):
    from fastapi.testclient import TestClient

    from api.main import app

    client = TestClient(app)
    url = "/sessions/s1/eval-experiments/exp-1/run"
    with patch("api.routers.eval_experiments.session_service") as svc:
        svc.run_eval_experiment.return_value = {
            "accepted": True,
            "experiment_id": "exp-1",
            "status": "running",
        }
        response = client.post(
            url,
            json={"background": True, "idempotency_key": "req-api", "timeout_seconds": 60},
            headers=auth_headers,
        )
        assert response.status_code == 202
        assert response.json()["accepted"] is True
        kwargs = svc.run_eval_experiment.call_args.kwargs
        assert kwargs["background"] is True
        assert kwargs["idempotency_key"] == "req-api"
        assert kwargs["timeout_seconds"] == 60

        svc.get_eval_experiment_status.return_value = {
            "experiment_id": "exp-1",
            "status": "running",
            "completed_cases": 1,
            "total_cases": 3,
        }
        status_response = client.get(
            "/sessions/s1/eval-experiments/exp-1/status", headers=auth_headers
        )
        assert status_response.status_code == 200
        assert status_response.json()["completed_cases"] == 1

        svc.run_eval_experiment.side_effect = ValueError("experiment already running: exp-1")
        conflict = client.post(url, json={"background": True}, headers=auth_headers)
        assert conflict.status_code == 409

        svc.run_eval_experiment.side_effect = ValueError("experiment not found")
        bad_request = client.post(url, json={"background": False}, headers=auth_headers)
        assert bad_request.status_code == 400
