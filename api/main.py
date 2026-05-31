# api/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    chat,
    eval,
    eval_datasets,
    eval_experiments,
    evidence,
    interrupts,
    oversight,
    redteam,
    reports,
    safety,
    session,
    stage,
    traces,
)
from core.config import settings
from core.execution_mode import WorkflowExecutionMode
from core.version import APP_STATUS, APP_VERSION
from storage.session_store import session_store

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库表
    session_store.initialize()
    logger.info("App started.")
    yield
    logger.info("App shutting down.")


app = FastAPI(
    title="AI Workflow Tool",
    description="Human-AI collaborative workflow tool for project inception",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/health")
def health():
    mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
    adapter_status = (
        "checkpoint_interrupt_enabled"
        if mode == WorkflowExecutionMode.LANGGRAPH_INTERRUPT
        else "mapping_available_single_step_default"
    )
    return {
        "status": "ok",
        "version": APP_VERSION,
        "app_status": APP_STATUS,
        "workflow_execution_mode": mode.value,
        "interrupt_adapter_status": adapter_status,
    }
