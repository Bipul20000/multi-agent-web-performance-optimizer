"""FastAPI application — entry point for the AWPIS backend."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from backend.config import get_settings
from backend.state import PipelineState
from backend.graph import run_pipeline, resume_pipeline
from backend.utils.shared import get_mongo, get_publisher, get_github
from backend.utils.github_client import GitHubClient
from backend.utils.mongo_client import MongoClient
from backend.utils.sse_publisher import SSEPublisher

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise shared clients on startup, tear them down on shutdown."""
    settings = get_settings()

    # ── MongoDB ────────────────────────────────────────────────────────
    mongo = get_mongo()
    try:
        if await mongo.ping():
            logger.info("✓ MongoDB connected")
        else:
            logger.warning("✗ MongoDB ping failed — continuing anyway")
    except Exception as exc:
        logger.warning("✗ MongoDB init error: {} — continuing anyway", exc)

    # ── Redis / SSE publisher ──────────────────────────────────────────
    sse = get_publisher()
    try:
        if await sse.ping():
            logger.info("✓ Redis connected")
        else:
            logger.warning("✗ Redis ping failed — continuing anyway")
    except Exception as exc:
        logger.warning("✗ Redis init error: {} — continuing anyway", exc)

    # ── GitHub ─────────────────────────────────────────────────────────
    github = get_github()
    if settings.GITHUB_TOKEN and settings.GITHUB_REPO:
        try:
            branch = await github.get_default_branch()
            logger.info("✓ GitHub connected — default branch: {}", branch)
        except Exception as exc:
            logger.warning("✗ GitHub connectivity check failed: {}", exc)
    else:
        logger.warning(
            "✗ GitHub client skipped — GITHUB_TOKEN or GITHUB_REPO not set"
        )

    # ── Store on app.state ─────────────────────────────────────────────
    application.state.mongo = mongo
    application.state.sse_publisher = sse
    application.state.github = github
    application.state.settings = settings

    logger.info("AWPIS backend started")

    yield  # ── Application runs ───────────────────────────────────────

    # ── Shutdown ───────────────────────────────────────────────────────
    logger.info("AWPIS backend shutting down…")

    await mongo.close()
    await sse.close()
    if github is not None:
        await github.close()

    logger.info("AWPIS backend stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AWPIS",
    description="Automated Website Performance Improvement System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Payload for POST /run."""

    website_url: str
    repo: str | None = None
    run_mode: str = "SUPERVISED"


class RunResponse(BaseModel):
    """Response for POST /run."""

    run_id: str
    status: str = "started"


class ApproveRequest(BaseModel):
    """Payload for POST /approve."""

    approved: bool
    reason: str = ""


class ScheduleRequest(BaseModel):
    """Payload for POST /schedule."""

    cron: str


class HealthCheck(BaseModel):
    """Response for GET /health."""

    status: str  # "ok" | "degraded"
    checks: dict[str, bool]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthCheck)
async def health(request: Request) -> HealthCheck:
    """Comprehensive health check — verifies MongoDB, Redis, and GitHub.

    Returns ``"ok"`` if all checks pass, ``"degraded"`` otherwise.
    """
    checks: dict[str, bool] = {
        "mongo": False,
        "redis": False,
        "github": False,
    }

    # MongoDB
    try:
        checks["mongo"] = await request.app.state.mongo.ping()
    except Exception:
        checks["mongo"] = False

    # Redis
    try:
        checks["redis"] = await request.app.state.sse_publisher.ping()
    except Exception:
        checks["redis"] = False

    # GitHub
    try:
        gh: GitHubClient | None = request.app.state.github
        if gh is not None:
            await gh.get_default_branch()
            checks["github"] = True
        else:
            checks["github"] = False
    except Exception:
        checks["github"] = False

    all_ok = all(checks.values())
    status = "ok" if all_ok else "degraded"

    logger.info("Health check: status={}, checks={}", status, checks)
    return HealthCheck(status=status, checks=checks)


@app.post("/run", response_model=RunResponse)
async def start_run(
    payload: RunRequest,
    request: Request,
) -> RunResponse:
    """Kick off a new AWPIS pipeline run."""
    run_id = uuid.uuid4().hex
    logger.info("Received run request: {} — run_id={}", payload, run_id)

    # Build full initial PipelineState with all required fields initialized
    settings = get_settings()
    repo = payload.repo or settings.GITHUB_REPO
    run_mode = payload.run_mode.upper()

    initial_state: PipelineState = {
        "run_id": run_id,
        "website_url": payload.website_url,
        "repo_path": repo,
        "run_mode": run_mode,
        "client_id": "",
        "psi_metrics": {},
        "business_priority": {},
        "file_map": {},
        "relevant_files": [],
        "forbidden_files": [],
        "recent_runs": [],
        "fix_memory": {},
        "baseline_scores": {},
        "agent_steps": [],
        "backend_metrics": [],
        "current_agent": "",
        "error_log": [],
    }

    mongo: MongoClient = request.app.state.mongo
    
    # Pre-save run record
    try:
        await mongo.save_run({
            "run_id": run_id,
            "website_url": payload.website_url,
            "repo_path": payload.repo,
            "run_mode": payload.run_mode,
            "status": "running"
        })
    except Exception as exc:
        logger.warning("Failed to pre-save run to Mongo: {}", exc)

    # Fire-and-forget background task
    async def _run_with_delay(state, r_id):
        await asyncio.sleep(2)  # give frontend time to connect SSE
        await run_pipeline(state, r_id)

    asyncio.create_task(
        _run_with_delay(initial_state, run_id),
        name=f"pipeline-{run_id}",
    )

    return RunResponse(run_id=run_id, status="started")


@app.post("/stop/{run_id}")
async def stop_run(run_id: str, request: Request):
    """Manually abort a running pipeline."""
    task_name = f"pipeline-{run_id}"
    canceled = False
    
    # Cancel the asyncio task
    for task in asyncio.all_tasks():
        if task.get_name() == task_name:
            task.cancel()
            canceled = True
            break
            
    # Update DB and emit event regardless of task finding (it might be stuck in DB)
    mongo: MongoClient = request.app.state.mongo
    sse = request.app.state.sse_publisher
    from backend.graph import get_graph
    app_graph = get_graph()
    state_tuple = app_graph.get_state({"configurable": {"thread_id": run_id}})
    agent_steps = state_tuple.values.get("agent_steps", []) if state_tuple and hasattr(state_tuple, "values") else []
    
    psi_metrics = state_tuple.values.get("psi_metrics", {}) if state_tuple and hasattr(state_tuple, "values") else {}
    backend_metrics = state_tuple.values.get("backend_metrics", []) if state_tuple and hasattr(state_tuple, "values") else {}
    
    summary_payload = {
        "deploy_status": "aborted",
        "agent_steps": agent_steps,
        "psi_metrics": psi_metrics,
        "backend_metrics": backend_metrics,
        "roi": {
            "message": "Pipeline was manually stopped by user."
        }
    }
    
    await mongo.update_run(run_id, {
        "status": "aborted",
        "deploy_status": "aborted",
        "run_summary": summary_payload
    })
    
    await sse.publish_run_complete(run_id, summary_payload)
    
    if canceled:
        logger.info(f"Successfully canceled task {task_name}")
        return {"status": "success", "message": f"Run {run_id} stopped."}
    else:
        logger.warning(f"Task {task_name} not found, but marked aborted in DB.")
        return {"status": "partial", "message": f"Run {run_id} marked aborted (task not found in memory)."}


@app.post("/approve/{run_id}")
async def approve_run(run_id: str, payload: ApproveRequest) -> dict[str, str]:
    """Resume a pipeline paused at a human gate."""
    logger.info("Human gate decision for run_id={}: approved={}", run_id, payload.approved)
    await resume_pipeline(run_id, {"approved": payload.approved, "reason": payload.reason})
    return {"status": "resumed", "run_id": run_id}


@app.get("/stream/{run_id}")
async def stream_events(run_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint — streams real-time agent step events for a run."""
    sse: SSEPublisher = request.app.state.sse_publisher

    async def _event_generator() -> AsyncGenerator[str, None]:
        async for chunk in sse.subscribe(run_id):
            if await request.is_disconnected():
                logger.info("SSE client disconnected for run_id={}", run_id)
                break
            yield chunk

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/runs")
async def list_runs(request: Request) -> list[dict[str, Any]]:
    """Return the last 10 run summaries from MongoDB."""
    mongo: MongoClient = request.app.state.mongo
    try:
        runs = await mongo.get_recent_runs(limit=10)
        logger.info("Returning {} runs", len(runs))
        return runs
    except Exception as exc:
        logger.error("Failed to fetch runs: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/run/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    """Return a single run by run_id."""
    mongo: MongoClient = request.app.state.mongo
    try:
        run = await mongo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return run
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to fetch run {}: {}", run_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/schedule")
async def configure_schedule(payload: ScheduleRequest) -> dict[str, str]:
    """Configure an APScheduler cron job for recurring pipeline runs.

    TODO: Wire up APScheduler with the cron expression.
    """
    logger.info("Schedule requested: {}", payload.cron)
    # TODO: integrate APScheduler
    return {"status": "scheduled", "cron": payload.cron}
