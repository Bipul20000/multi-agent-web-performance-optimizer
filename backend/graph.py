"""LangGraph definition — orchestrates the multi-agent pipeline."""

import asyncio
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langchain_core.runnables import RunnableConfig
from loguru import logger

from backend.utils.shared import get_publisher, get_mongo

from backend.agents import (
    backend_fix_agent,
    codebase_agent,
    context_agent,
    critic_agent,
    dependency_gate,
    deploy_agent,
    frontend_fix_agent,
    history_agent,
    learning_agent,
    metrics_agent,
    quality_gate,
    reasoning_agent,
    report_agent,
    risk_classifier,
    sandbox_agent,
    syntax_gate,
)
from backend.state import PipelineState

# ─── LAYER 2: Parallel fan-out ───

async def gather_intelligence(state: PipelineState) -> dict:
    """Pass-through router node to start parallel intelligence gathering."""
    return {"current_agent": "gathering"}

async def merge_intelligence(state: PipelineState) -> dict:
    """Waits for all 4 intelligence agents to complete and merges state."""
    pages_scanned = len(state.get("psi_metrics", {}))
    files_mapped = len(state.get("file_map", {}).get("categorized", {}).get("frontend_critical", []))
    logger.info(f"Intelligence gathered: {pages_scanned} pages, {files_mapped} frontend files")
    return {"current_agent": "intelligence_merged"}


# ─── LAYER 3: Reasoning ───

def route_after_risk(state: PipelineState) -> Literal["fix_generation", "human_gate", "skip_run"]:
    """Route after risk classification based on risk level and confidence."""
    risk = state.get("risk_classification", "LOW")
    confidence = state.get("confidence_score", 0.0)
    if confidence < 0.3:
        return "skip_run"
    if risk == "HIGH":
        return "human_gate"
    return "fix_generation"


async def human_gate_node(state: PipelineState) -> dict:
    """Pauses the graph to wait for human approval on high-risk fixes."""
    decision = interrupt({
        "message": "High risk fix requires approval",
        "fix_plan": state.get("fix_plan", {}),
        "risk_classification": state.get("risk_classification"),
        "confidence_score": state.get("confidence_score")
    })
    return {"human_approved": decision.get("approved", False)}


def route_after_human(state: PipelineState) -> Literal["fix_generation", "skip_run"]:
    """Proceed if human approved, otherwise skip."""
    return "fix_generation" if state.get("human_approved") else "skip_run"


async def skip_run(state: PipelineState) -> dict:
    """Terminal state when run is rejected or low confidence."""
    logger.info("Run skipped — low confidence or rejected")
    run_id = state.get("run_id")
    if run_id:
        sse = get_publisher()
        mongo = get_mongo()
        
        agent_steps = state.get("agent_steps", [])
        psi_metrics = state.get("psi_metrics", {})
        backend_metrics = state.get("backend_metrics", [])
        
        summary_payload = {
            "deploy_status": "skipped",
            "agent_steps": agent_steps,
            "psi_metrics": psi_metrics,
            "backend_metrics": backend_metrics,
            "roi": {
                "message": "Run was skipped due to low confidence or rejection."
            }
        }
        
        await sse.publish_run_complete(run_id, summary_payload)
        await mongo.update_run(run_id, {
            "status": "skipped",
            "deploy_status": "skipped",
            "run_summary": summary_payload
        })
    return {"deploy_status": "skipped", "current_agent": "done"}


# ─── LAYER 4: Fix Generation (parallel) ───

async def fix_generation(state: PipelineState) -> dict:
    """Pass-through to trigger parallel fix agents."""
    return {"current_agent": "generating_fixes"}


async def merge_fixes(state: PipelineState) -> dict:
    """Merge parallel fix outputs before quality gates."""
    return {"current_agent": "fixes_merged"}


# ─── LAYER 5: Quality Gates (sequential) ───

def route_syntax_gate(state: PipelineState) -> Literal["quality_gate", "retry_fix"]:
    """If syntax passes, move to quality gate, else retry."""
    return "quality_gate" if state.get("syntax_gate") == "PASS" else "retry_fix"


def route_quality_gate(state: PipelineState) -> Literal["critic_agent", "retry_fix"]:
    """If quality passes, move to critic, else retry."""
    return "critic_agent" if state.get("quality_gate") == "PASS" else "retry_fix"


def route_critic_gate(state: PipelineState) -> Literal["dependency_gate", "retry_fix"]:
    """If critic approves, move to dependency check, else retry."""
    return "dependency_gate" if state.get("critic_gate") == "APPROVE" else "retry_fix"


def route_dependency_gate(state: PipelineState) -> Literal["sandbox_agent", "expand_fix_scope"]:
    """If dependencies clear, sandbox it, else expand scope."""
    return "sandbox_agent" if state.get("dependency_gate") == "CLEAR" else "expand_fix_scope"


async def retry_fix(state: PipelineState) -> dict:
    """Increment retry counter when a gate fails."""
    retry_count = state.get("retry_count", 0) + 1
    if retry_count >= 3:
        return {"deploy_status": "failed_gates", "retry_count": retry_count}
    return {"retry_count": retry_count}


def route_after_retry(state: PipelineState) -> Literal["fix_generation", "skip_run"]:
    """Loop back to fix generation, or skip if retries exhausted."""
    return "skip_run" if state.get("retry_count", 0) >= 3 else "fix_generation"


async def expand_fix_scope(state: PipelineState) -> dict:
    """Dummy node: Expand scope if dependencies not clear, and retry fix."""
    return {"current_agent": "expanding_scope"}


# ─── LAYER 6: Sandbox + Deploy ───

def route_sandbox(state: PipelineState) -> Literal["deploy_agent", "sandbox_rejected"]:
    """Deploy if sandbox passed, else reject."""
    return "deploy_agent" if state.get("sandbox_gate") == "APPROVE" else "sandbox_rejected"


async def sandbox_rejected(state: PipelineState) -> dict:
    """Terminal state when sandbox fails."""
    run_id = state.get("run_id")
    if run_id:
        sse = get_publisher()
        mongo = get_mongo()
        
        config = {"configurable": {"thread_id": run_id}}
        state_tuple = app_graph.get_state(config)
        agent_steps = state_tuple.values.get("agent_steps", []) if state_tuple and hasattr(state_tuple, "values") else []
        psi_metrics = state_tuple.values.get("psi_metrics", {}) if state_tuple and hasattr(state_tuple, "values") else {}
        backend_metrics = state_tuple.values.get("backend_metrics", []) if state_tuple and hasattr(state_tuple, "values") else []
        
        summary_payload = {
            "deploy_status": "sandbox_failed",
            "agent_steps": agent_steps,
            "psi_metrics": psi_metrics,
            "backend_metrics": backend_metrics,
            "roi": {
                "message": "Pipeline halted due to Sandbox test failure."
            }
        }
        await sse.publish_run_complete(run_id, summary_payload)
        await mongo.update_run(run_id, {"status": "sandbox_failed", "run_summary": summary_payload})
    return {"deploy_status": "sandbox_failed", "current_agent": "done"}


# ─── GRAPH COMPILATION ───

builder = StateGraph(PipelineState)

# Add all nodes
builder.add_node("gather_intelligence", gather_intelligence)
builder.add_node("metrics_agent", metrics_agent.run)
builder.add_node("codebase_agent", codebase_agent.run)
builder.add_node("history_agent", history_agent.run)
builder.add_node("context_agent", context_agent.run)
builder.add_node("merge_intelligence", merge_intelligence)

builder.add_node("reasoning_agent", reasoning_agent.run)
builder.add_node("risk_classifier", risk_classifier.run)
builder.add_node("human_gate", human_gate_node)
builder.add_node("skip_run", skip_run)

builder.add_node("fix_generation", fix_generation)
builder.add_node("frontend_fix_agent", frontend_fix_agent.run)
builder.add_node("backend_fix_agent", backend_fix_agent.run)
builder.add_node("merge_fixes", merge_fixes)

builder.add_node("syntax_gate", syntax_gate.run)
builder.add_node("quality_gate", quality_gate.run)
builder.add_node("critic_agent", critic_agent.run)
builder.add_node("dependency_gate", dependency_gate.run)
builder.add_node("retry_fix", retry_fix)
builder.add_node("expand_fix_scope", expand_fix_scope)

builder.add_node("sandbox_agent", sandbox_agent.run)
builder.add_node("sandbox_rejected", sandbox_rejected)
builder.add_node("deploy_agent", deploy_agent.run)
builder.add_node("learning_agent", learning_agent.run)
builder.add_node("report_agent", report_agent.run)

# Set up edges
builder.add_edge(START, "gather_intelligence")

# Layer 2 parallel fan-out
builder.add_edge("gather_intelligence", "metrics_agent")
builder.add_edge("gather_intelligence", "codebase_agent")
builder.add_edge("gather_intelligence", "history_agent")
builder.add_edge("gather_intelligence", "context_agent")

builder.add_edge("metrics_agent", "merge_intelligence")
builder.add_edge("codebase_agent", "merge_intelligence")
builder.add_edge("history_agent", "merge_intelligence")
builder.add_edge("context_agent", "merge_intelligence")

# Layer 3 reasoning
builder.add_edge("merge_intelligence", "reasoning_agent")
builder.add_edge("reasoning_agent", "risk_classifier")

builder.add_conditional_edges("risk_classifier", route_after_risk)
builder.add_conditional_edges("human_gate", route_after_human)
builder.add_edge("skip_run", END)

# Layer 4 fix generation
builder.add_edge("fix_generation", "frontend_fix_agent")
builder.add_edge("fix_generation", "backend_fix_agent")
builder.add_edge("frontend_fix_agent", "merge_fixes")
builder.add_edge("backend_fix_agent", "merge_fixes")

# Layer 5 quality gates
builder.add_edge("merge_fixes", "syntax_gate")
builder.add_conditional_edges("syntax_gate", route_syntax_gate)
builder.add_conditional_edges("quality_gate", route_quality_gate)
builder.add_conditional_edges("critic_agent", route_critic_gate)
builder.add_conditional_edges("dependency_gate", route_dependency_gate)

builder.add_edge("expand_fix_scope", "merge_fixes")
builder.add_conditional_edges("retry_fix", route_after_retry)

# Layer 6 sandbox + deploy
builder.add_conditional_edges("sandbox_agent", route_sandbox)
builder.add_edge("sandbox_rejected", END)
builder.add_edge("deploy_agent", "learning_agent")
builder.add_edge("deploy_agent", "report_agent")

# Layer 7 learning + report
builder.add_edge("learning_agent", END)
builder.add_edge("report_agent", END)

# Compile graph
checkpointer = MemorySaver()
app_graph = builder.compile(checkpointer=checkpointer, interrupt_before=["human_gate"])


def get_graph():
    """Return the compiled LangGraph application."""
    return app_graph


async def run_pipeline(initial_state: PipelineState, run_id: str) -> dict:
    """Entry point called by main.py background task."""
    config: RunnableConfig = {"configurable": {"thread_id": run_id}}
    try:
        result = await app_graph.ainvoke(initial_state, config=config)
        return result
    except Exception as exc:
        logger.exception("Pipeline unhandled exception for run_id={}", run_id)
        sse = get_publisher()
        mongo = get_mongo()
        
        err_msg = str(exc)
        
        state_tuple = app_graph.get_state({"configurable": {"thread_id": run_id}})
        agent_steps = state_tuple.values.get("agent_steps", []) if state_tuple and hasattr(state_tuple, "values") else []
        
        psi_metrics = state_tuple.values.get("psi_metrics", {}) if state_tuple and hasattr(state_tuple, "values") else {}
        backend_metrics = state_tuple.values.get("backend_metrics", []) if state_tuple and hasattr(state_tuple, "values") else []
        
        # Build a safe summary structure so the frontend History tab has something to display
        summary_payload = {
            "deploy_status": "failed",
            "agent_steps": agent_steps,
            "psi_metrics": psi_metrics,
            "backend_metrics": backend_metrics,
            "roi": {
                "message": f"Pipeline crashed: {err_msg}"
            }
        }
        
        await sse.publish_run_complete(run_id, summary_payload)
        await mongo.update_run(run_id, {
            "status": "failed", 
            "deploy_status": "failed",
            "run_summary": summary_payload
        })
        return {"error": err_msg}


async def resume_pipeline(run_id: str, human_decision: dict) -> dict:
    """Called by /approve endpoint to resume after human gate."""
    config: RunnableConfig = {"configurable": {"thread_id": run_id}}
    result = await app_graph.ainvoke(Command(resume=human_decision), config=config)
    return result
