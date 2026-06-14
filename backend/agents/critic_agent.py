"""Critic agent — adversarial LLM reviewer."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from loguru import logger

from backend.config import get_settings
from backend.state import PipelineState
from backend.utils.gemini_client import call_with_structured_output, get_groq_reasoning_model
from backend.utils.shared import get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the AI critic gate."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "critic_agent", "Adversarial AI review of generated code")

        from backend.config import get_settings
        demo_mode = get_settings().DEMO_MODE.lower() == "true"
        if demo_mode:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "critic_gate", "APPROVE", "DEMO MODE: auto-approved")
            await sse.publish_agent_complete(run_id, "critic_agent", "DEMO MODE: auto-approved", duration_ms)
            return {
                "critic_gate": "APPROVE",
                "agent_steps": [{
                    "agent": "critic_agent",
                    "status": "complete",
                    "summary": "DEMO MODE: auto-approved",
                    "duration_ms": duration_ms
                }],
                "current_agent": "critic_agent"
            }

        fixes = state.get("generated_fixes", [])
        if not fixes:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "critic_gate", "APPROVE", "No fixes to review")
            await sse.publish_agent_complete(run_id, "critic_agent", "APPROVE", duration_ms)
            return {
                "critic_gate": "APPROVE",
                "agent_steps": [{
                    "agent": "critic_agent",
                    "status": "complete",
                    "summary": "Approved (no fixes)",
                    "duration_ms": duration_ms
                }],
                "current_agent": "critic_agent"
            }

        fix_plan = state.get("fix_plan", {})
        
        # Build payload
        fixes_payload = []
        for fix in fixes:
            fixes_payload.append({
                "path": fix.get("path"),
                "change_summary": fix.get("change_summary"),
                "original_content": fix.get("original_content", "")[:2000] + "\n... (truncated)",  # Keep it manageable
                "new_content": fix.get("new_content", "")[:2000] + "\n... (truncated)"
            })
            
        USER_PROMPT = f"""
## Fix Plan Context
Target Metric: {fix_plan.get('target_metric')}
Root Cause: {fix_plan.get('root_cause')}
Fix Category: {fix_plan.get('fix_category')}

## Generated Fixes
{json.dumps(fixes_payload, indent=2)}

Please evaluate the code changes.
"""

        SYSTEM_PROMPT = """You are an adversarial code reviewer. Your job is to find problems, 
not approve fixes. Be skeptical.

Evaluate the following:
1. Does the fix actually address the stated root_cause in fix_plan?
2. Does any change introduce a new performance regression?
3. Is there a simpler change that achieves the same goal?
4. Are there any subtle bugs introduced?
"""

        CRITIC_SCHEMA = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "description": "APPROVE or REJECT"},
                "issues": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "simpler_alternative": {"type": ["string", "null"]},
                "reasoning": {"type": "string"}
            },
            "required": ["verdict", "issues", "simpler_alternative", "reasoning"]
        }

        model = get_groq_reasoning_model(get_settings().GROQ_API_KEY)
        review = await call_with_structured_output(model, SYSTEM_PROMPT, USER_PROMPT, CRITIC_SCHEMA)
        
        verdict = review.get("verdict", "REJECT").upper()
        if verdict not in ("APPROVE", "REJECT"):
            verdict = "REJECT"

        # Update state
        critic_feedback = review.get("reasoning", "")
        if review.get("issues"):
            critic_feedback += "\nIssues: " + ", ".join(review["issues"])
            
        updated_fix_plan = dict(fix_plan)
        if review.get("simpler_alternative"):
            updated_fix_plan["_critic_suggestion"] = review["simpler_alternative"]

        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        await sse.publish_gate_result(run_id, "critic_gate", verdict, critic_feedback)
        await sse.publish_agent_complete(run_id, "critic_agent", f"{verdict}: {critic_feedback[:100]}...", duration_ms)

        return {
            "critic_gate": verdict,
            "critic_feedback": critic_feedback,
            "fix_plan": updated_fix_plan,
            "agent_steps": [{
                "agent": "critic_agent",
                "status": "complete",
                "summary": verdict,
                "duration_ms": duration_ms
            }],
            "current_agent": "critic_agent"
        }

    except Exception as exc:
        logger.exception("Critic agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "critic_agent", str(exc), duration_ms)
        await sse.publish_gate_result(run_id, "critic_gate", "REJECT", f"Internal error: {exc}")
        
        return {
            "critic_gate": "REJECT",
            "error_log": [f"critic_agent error: {exc}"],
            "agent_steps": [{
                "agent": "critic_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "critic_agent"
        }
