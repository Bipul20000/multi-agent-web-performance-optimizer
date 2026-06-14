"""Quality gate agent — performs structural heuristics to catch poor code quality."""

from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_publisher


def _calculate_max_nesting(content: str) -> int:
    """Proxy for cognitive complexity: measures max brace/parentheses nesting depth."""
    max_depth = 0
    current_depth = 0
    for char in content:
        if char in "{([":
            current_depth += 1
            if current_depth > max_depth:
                max_depth = current_depth
        elif char in "})]":
            current_depth = max(0, current_depth - 1)
    return max_depth


def _check_duplication(content1: str, content2: str) -> bool:
    """Checks if there are 20+ identical consecutive lines between two contents."""
    lines1 = [l.strip() for l in content1.split("\n") if l.strip()]
    lines2 = [l.strip() for l in content2.split("\n") if l.strip()]
    
    if len(lines1) < 20 or len(lines2) < 20:
        return False
        
    for i in range(len(lines1) - 19):
        block = lines1[i:i+20]
        block_str = "\n".join(block)
        
        # Super naive sliding window
        for j in range(len(lines2) - 19):
            if block_str == "\n".join(lines2[j:j+20]):
                return True
    return False


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the code quality heuristic gate."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "quality_gate", "Validating code quality metrics")

        from backend.config import get_settings
        demo_mode = get_settings().DEMO_MODE.lower() == "true"
        if demo_mode:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "quality_gate", "PASS", "DEMO MODE: auto-approved")
            await sse.publish_agent_complete(run_id, "quality_gate", "DEMO MODE: auto-approved", duration_ms)
            return {
                "quality_gate": "PASS",
                "agent_steps": [{
                    "agent": "quality_gate",
                    "status": "complete",
                    "summary": "DEMO MODE: auto-approved",
                    "duration_ms": duration_ms
                }],
                "current_agent": "quality_gate"
            }

        fixes = state.get("generated_fixes", [])
        if not fixes:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "quality_gate", "PASS", "No fixes to check")
            await sse.publish_agent_complete(run_id, "quality_gate", "PASS", duration_ms)
            return {
                "quality_gate": "PASS",
                "agent_steps": [{
                    "agent": "quality_gate",
                    "status": "complete",
                    "summary": "Passed (no fixes)",
                    "duration_ms": duration_ms
                }],
                "current_agent": "quality_gate"
            }

        failed_rules = []

        for i, fix in enumerate(fixes):
            path = fix.get("path", "")
            original = fix.get("original_content", "")
            new_content = fix.get("new_content", "")
            
            # Rule 1: Cognitive complexity (nesting depth)
            if _calculate_max_nesting(new_content) > 10:
                failed_rules.append(f"{path}: Nesting depth exceeds 10 (too complex)")
                
            # Rule 2: Introduced TODO/FIXME/HACK
            for tag in ["TODO", "FIXME", "HACK"]:
                if tag in new_content and tag not in original:
                    failed_rules.append(f"{path}: Introduced new {tag} comment")
                    
            # Rule 3: TypeScript 'any' leak
            if path.endswith((".ts", ".tsx")):
                orig_anys = original.count(" any ") + original.count(":any ") + original.count(": any")
                new_anys = new_content.count(" any ") + new_content.count(":any ") + new_content.count(": any")
                if new_anys > orig_anys:
                    failed_rules.append(f"{path}: Introduced new 'any' types")
                    
            # Rule 4: Wildcard imports
            if "import * from" in new_content and "import * from" not in original:
                failed_rules.append(f"{path}: Introduced wildcard import")
                
            # Rule 5: File growth
            orig_lines = len(original.split("\n"))
            new_lines = len(new_content.split("\n"))
            if orig_lines > 10 and new_lines > (orig_lines * 1.5):
                failed_rules.append(f"{path}: File size increased by >50%")

            # Rule 6: Duplication check across generated fixes
            for j, other_fix in enumerate(fixes):
                if i != j:
                    if _check_duplication(new_content, other_fix.get("new_content", "")):
                        failed_rules.append(f"{path}: High code duplication with {other_fix.get('path')}")
                        break

        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        if failed_rules:
            result = "FAIL"
            details = "\n".join(failed_rules)
        else:
            result = "PASS"
            details = "All files passed quality heuristics"
            
        await sse.publish_gate_result(run_id, "quality_gate", result, details)
        await sse.publish_agent_complete(run_id, "quality_gate", f"{result}: {details}", duration_ms)

        return {
            "quality_gate": result,
            "agent_steps": [{
                "agent": "quality_gate",
                "status": "complete",
                "summary": result,
                "duration_ms": duration_ms
            }],
            "current_agent": "quality_gate"
        }

    except Exception as exc:
        logger.exception("Quality gate failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "quality_gate", str(exc), duration_ms)
        await sse.publish_gate_result(run_id, "quality_gate", "FAIL", f"Internal error: {exc}")
        
        return {
            "quality_gate": "FAIL",
            "error_log": [f"quality_gate error: {exc}"],
            "agent_steps": [{
                "agent": "quality_gate",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "quality_gate"
        }
