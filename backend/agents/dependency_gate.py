"""Dependency gate agent — pure graph traversal to check downstream impacts."""

from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the downstream dependency impact check."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "dependency_gate", "Mapping downstream dependency impacts")

        from backend.config import get_settings
        demo_mode = get_settings().DEMO_MODE.lower() == "true"
        if demo_mode:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "dependency_gate", "CLEAR", "DEMO MODE: auto-approved")
            await sse.publish_agent_complete(run_id, "dependency_gate", "DEMO MODE: auto-approved", duration_ms)
            return {
                "dependency_gate": "CLEAR",
                "agent_steps": [{
                    "agent": "dependency_gate",
                    "status": "complete",
                    "summary": "DEMO MODE: auto-approved",
                    "duration_ms": duration_ms
                }],
                "current_agent": "dependency_gate"
            }

        fixes = state.get("generated_fixes", [])
        if not fixes:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "dependency_gate", "CLEAR", "No fixes to check")
            await sse.publish_agent_complete(run_id, "dependency_gate", "CLEAR", duration_ms)
            return {
                "dependency_gate": "CLEAR",
                "agent_steps": [{
                    "agent": "dependency_gate",
                    "status": "complete",
                    "summary": "Passed (no fixes)",
                    "duration_ms": duration_ms
                }],
                "current_agent": "dependency_gate"
            }

        file_map = state.get("file_map", {})
        file_contents = file_map.get("file_contents", {})
        forbidden_files = set(state.get("forbidden_files", []))
        
        impacted = False
        downstream_risk = []
        
        for fix in fixes:
            changed_path = fix.get("path", "")
            # Basic module name extraction (e.g., components/Hero.tsx -> Hero)
            filename = changed_path.split("/")[-1].split(".")[0]
            
            downstream_files = []
            
            # Scan all files for import references
            for other_path, content in file_contents.items():
                if other_path == changed_path:
                    continue
                    
                # Very naive import check
                if f"from '{filename}'" in content or f"from \"{filename}\"" in content or f"from './{filename}'" in content or f"from '../{filename}'" in content:
                    downstream_files.append(other_path)
                    
            if len(downstream_files) >= 3:
                impacted = True
                downstream_risk.extend(downstream_files)
                
            if any(f in forbidden_files for f in downstream_files):
                impacted = True
                downstream_risk.extend(downstream_files)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        if impacted:
            result = "IMPACTED"
            details = f"Changed files impact {len(downstream_risk)} downstream files."
        else:
            result = "CLEAR"
            details = "Downstream dependencies clear"
            
        updated_fix_plan = dict(state.get("fix_plan", {}))
        if downstream_risk:
            updated_fix_plan["_downstream_risk"] = list(set(downstream_risk))
            
        await sse.publish_gate_result(run_id, "dependency_gate", result, details)
        await sse.publish_agent_complete(run_id, "dependency_gate", f"{result}: {details}", duration_ms)

        return {
            "dependency_gate": result,
            "fix_plan": updated_fix_plan,
            "agent_steps": [{
                "agent": "dependency_gate",
                "status": "complete",
                "summary": result,
                "duration_ms": duration_ms
            }],
            "current_agent": "dependency_gate"
        }

    except Exception as exc:
        logger.exception("Dependency gate failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "dependency_gate", str(exc), duration_ms)
        await sse.publish_gate_result(run_id, "dependency_gate", "IMPACTED", f"Internal error: {exc}")
        
        return {
            "dependency_gate": "IMPACTED",
            "error_log": [f"dependency_gate error: {exc}"],
            "agent_steps": [{
                "agent": "dependency_gate",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "dependency_gate"
        }
