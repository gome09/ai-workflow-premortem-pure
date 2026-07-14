# api/main.py
import json
import logging
import sys
from contextlib import asynccontextmanager

import redis as redis_lib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.routers import (
    chat,
    eval,
    eval_datasets,
    eval_experiments,
    evidence,
    governance,
    interrupts,
    oversight,
    redteam,
    reports,
    safety,
    session,
    stage,
    traces,
)
from auth.router import router as auth_router
from core.audit_service import append_audit_event
from core.config import settings
from core.execution_mode import WorkflowExecutionMode
from core.version import APP_STATUS, APP_VERSION
from scenarios import list_scenarios
from storage.field_security import is_encryption_enabled
from storage.session_store import session_store

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:

    class Instrumentator:  # type: ignore[override]
        """No-op fallback used when Prometheus instrumentation is unavailable."""

        def instrument(self, app: FastAPI):
            return self

        def expose(self, app: FastAPI, endpoint: str = "/metrics", include_in_schema: bool = False):
            return app


class _JSONFormatter(logging.Formatter):
    """stdlib-only JSON log formatter — Docker log drivers consume structured output."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JSONFormatter())
logging.basicConfig(level=settings.log_level.upper(), handlers=[_handler], force=True)
logger = logging.getLogger(__name__)


_instrumentator = Instrumentator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    session_store.initialize()
    _instrumentator.expose(app, endpoint="/metrics", include_in_schema=False)
    # T3.5 启动时刷新业务 Gauge 指标（prometheus_client 默认 REGISTRY 已通过
    # instrumentator 的 /metrics 端点一并暴露）
    try:
        from api.metrics import refresh_gauge_metrics

        refresh_gauge_metrics()
    except Exception:
        logger.warning("refresh_gauge_metrics failed on startup; non-fatal", exc_info=True)
    logger.info("App started.")
    yield
    logger.info("App shutting down.")


app = FastAPI(
    title="AI Workflow Tool",
    description="Human-AI collaborative workflow tool for project inception",
    version=APP_VERSION,
    lifespan=lifespan,
)

# Prometheus metrics — instrument before middleware, expose in lifespan
_instrumentator.instrument(app)

# Rate limiting: decorator-only pattern (not global middleware).
# Each protected route uses @limiter.limit(...) explicitly.
# app.state.limiter is required by slowapi to resolve the limiter instance at request time.
app.state.limiter = limiter


def _rate_limit_audit_handler(request, exc):
    """T2.1 LLM10: 429 事件记入审计日志（接入 audit_service），作为租户级滥用证据。"""
    try:
        session_id = (request.path_params or {}).get("session_id") or ""
        if session_id:
            ctx = session_store.load(session_id)
            if ctx is not None:
                append_audit_event(
                    ctx,
                    actor="system",
                    event_type="rate_limit_exceeded",
                    target_type="tenant",
                    target_id=getattr(ctx, "tenant_id", "") or "unknown",
                    metadata={
                        "path": request.url.path,
                        "method": request.method,
                        "client": request.client.host if request.client else "",
                        "limit_detail": str(getattr(exc, "limit", "")),
                    },
                )
                session_store.save(ctx)
    except Exception:
        logger.warning("Could not persist rate_limit_exceeded audit event", exc_info=True)
    return _rate_limit_exceeded_handler(request, exc)


app.add_exception_handler(RateLimitExceeded, _rate_limit_audit_handler)

origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(session.router)
app.include_router(stage.router)
app.include_router(chat.router)
app.include_router(oversight.router)
app.include_router(interrupts.router)
app.include_router(evidence.router)
app.include_router(safety.router)
app.include_router(reports.router)
app.include_router(eval.router)
app.include_router(eval_datasets.router)
app.include_router(eval_experiments.router)
app.include_router(redteam.router)
app.include_router(traces.router)
app.include_router(governance.router)


@app.get("/health/live", include_in_schema=False)
def health_live():
    """Liveness probe — confirms process is up. No I/O."""
    return {"status": "ok", "version": APP_VERSION}


@app.get("/health/ready", include_in_schema=False)
def health_ready():
    """Readiness probe — verifies primary storage and Redis connectivity (Redis skipped in sqlite mode)."""
    checks: dict[str, str] = {}
    overall_ok = True

    try:
        with session_store._get_conn() as conn:
            conn.execute("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"
        overall_ok = False

    if settings.storage_backend != "sqlite":
        try:
            r = redis_lib.from_url(settings.redis_url, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            overall_ok = False
    else:
        checks["redis"] = "skipped (sqlite mode)"

    status_code = 200 if overall_ok else 503
    body = {"status": "ready" if overall_ok else "degraded", "checks": checks}
    return JSONResponse(content=body, status_code=status_code)


@app.get("/health")
def health():
    """Legacy health endpoint — kept for backward compatibility."""
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    return {
        "status": "ok",
        "version": APP_VERSION,
        "app_status": APP_STATUS,
        "workflow_execution_mode": mode.value,
        "default_domain_profile": settings.domain_profile,
        "default_scenario_id": settings.default_scenario_id or None,
        "builtin_scenarios": [item.scenario_id for item in list_scenarios()],
        "data_encryption": "enabled" if is_encryption_enabled() else "disabled",
        "audit_retention_days": settings.audit_retention_days,
        "session_retention_days": settings.session_retention_days,
        "gate_rules_disabled": sorted(settings.gate_rules_disabled_set)
        if settings.gate_rules_disabled_set
        else [],
    }
