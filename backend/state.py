"""LangGraph PipelineState — the single TypedDict that flows through every node."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


def _reduce_last(a: str, b: str) -> str:
    return b

class PipelineState(TypedDict, total=False):
    """Complete state schema for the AWPIS LangGraph pipeline.

    Every agent reads from / writes to a subset of these fields.
    Fields use ``total=False`` so agents can return partial updates.
    """

    # ── Run metadata ───────────────────────────────────────
    run_id: str
    client_id: str
    website_url: str
    repo_path: str
    run_mode: str  # "SUPERVISED" | "AUTOMATED"

    # ── Metrics & baselines ────────────────────────────────
    psi_metrics: dict
    backend_metrics: list
    baseline_scores: dict
    business_priority: dict

    # ── Codebase analysis ──────────────────────────────────
    file_map: dict
    relevant_files: list
    forbidden_files: list

    # ── History & memory ───────────────────────────────────
    recent_runs: list
    fix_memory: dict

    # ── Reasoning & planning ───────────────────────────────
    fix_plan: dict
    risk_classification: str
    confidence_score: float
    human_approved: bool

    # ── Fix generation & review ────────────────────────────
    generated_fixes: Annotated[list, operator.add]
    critic_feedback: str
    retry_count: int

    # ── Quality gates ──────────────────────────────────────
    syntax_gate: str
    quality_gate: str
    critic_gate: str
    dependency_gate: str

    # ── Sandbox testing ────────────────────────────────────
    sandbox_url: str
    sandbox_psi: dict
    sandbox_gate: str

    # ── Deployment ─────────────────────────────────────────
    pr_url: str
    deploy_status: str
    production_psi_after: dict
    auto_reverted: bool

    # ── Observability ──────────────────────────────────────
    langsmith_trace_id: str
    error_log: Annotated[list, operator.add]
    total_duration_ms: int

    # ── SSE streaming to UI ────────────────────────────────
    current_agent: Annotated[str, _reduce_last]
    agent_steps: Annotated[list, operator.add]
