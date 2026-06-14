"""Syntax gate agent — performs fast static analysis on generated code."""

from __future__ import annotations

import os
import re
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_publisher

SECRET_PATTERNS = [
    r"api_key\s*=\s*['\"][a-zA-Z0-9_\-]+['\"]",
    r"secret\s*=\s*['\"][a-zA-Z0-9_\-]+['\"]",
    r"password\s*=\s*['\"][a-zA-Z0-9_\-]+['\"]",
    r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*",
    r"sk-[a-zA-Z0-9]{20,}",
    r"AKIA[0-9A-Z]{16}",
]

DANGEROUS_CALLS = [
    r"\beval\s*\(",
    r"document\.write\s*\(",
    r"dangerouslySetInnerHTML",
]

CONSOLE_CALLS = [
    r"console\.log\s*\(",
    r"console\.warn\s*\(",
    r"console\.error\s*\(",
]


def _check_tag_balance(content: str) -> bool:
    """Super basic JSX/TSX tag balance check."""
    # Matches <Tag> and </Tag> (ignores self-closing and attributes)
    open_tags = re.findall(r"<([a-zA-Z0-9_]+)(?:[^>]*[^\/])?>", content)
    close_tags = re.findall(r"</([a-zA-Z0-9_]+)>", content)
    
    # Just check if counts match roughly, as proper parsing is complex
    # This is a heuristic
    open_counts = {}
    for t in open_tags:
        open_counts[t] = open_counts.get(t, 0) + 1
        
    for t in close_tags:
        if t not in open_counts or open_counts[t] <= 0:
            return False  # Unmatched close tag
        open_counts[t] -= 1
        
    return True


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the syntax validation gate."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "syntax_gate", "Validating code syntax and security")

        from backend.config import get_settings
        demo_mode = get_settings().DEMO_MODE.lower() == "true"
        if demo_mode:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "syntax_gate", "PASS", "DEMO MODE: auto-approved")
            await sse.publish_agent_complete(run_id, "syntax_gate", "DEMO MODE: auto-approved", duration_ms)
            return {
                "syntax_gate": "PASS",
                "agent_steps": [{
                    "agent": "syntax_gate",
                    "status": "complete",
                    "summary": "DEMO MODE: auto-approved",
                    "duration_ms": duration_ms
                }],
                "current_agent": "syntax_gate"
            }

        fixes = state.get("generated_fixes", [])
        if not fixes:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "syntax_gate", "PASS", "No fixes to check")
            await sse.publish_agent_complete(run_id, "syntax_gate", "PASS", duration_ms)
            return {
                "syntax_gate": "PASS",
                "agent_steps": [{
                    "agent": "syntax_gate",
                    "status": "complete",
                    "summary": "Passed (no fixes)",
                    "duration_ms": duration_ms
                }],
                "current_agent": "syntax_gate"
            }

        failed_rules = []

        for fix in fixes:
            path = fix.get("path", "")
            content = fix.get("new_content", "")
            
            # Rule 1: Empty file check
            if not content or not content.strip():
                failed_rules.append(f"{path}: File is empty")
                continue
                
            # Rule 2: Hardcoded secrets
            for pattern in SECRET_PATTERNS:
                if re.search(pattern, content):
                    failed_rules.append(f"{path}: Possible hardcoded secret found")
                    break
                    
            # Rule 3: Dangerous calls
            for pattern in DANGEROUS_CALLS:
                if re.search(pattern, content):
                    failed_rules.append(f"{path}: Dangerous function call found")
                    break
                    
            # Rule 4: Console logs
            for pattern in CONSOLE_CALLS:
                if re.search(pattern, content):
                    failed_rules.append(f"{path}: Console log statement left in code")
                    break
                    
            # Rule 5: JSX balance
            if path.endswith((".tsx", ".jsx")):
                if not _check_tag_balance(content):
                    failed_rules.append(f"{path}: Unbalanced JSX tags")
                    
            # Rule 6: Next.js config export
            if path.startswith("next.config."):
                if "module.exports" not in content and "export default" not in content:
                    failed_rules.append(f"{path}: next.config missing default export")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        if failed_rules:
            result = "FAIL"
            details = "\n".join(failed_rules)
        else:
            result = "PASS"
            details = "All files passed syntax checks"
            
        await sse.publish_gate_result(run_id, "syntax_gate", result, details)
        await sse.publish_agent_complete(run_id, "syntax_gate", f"{result}: {details}", duration_ms)

        return {
            "syntax_gate": result,
            "agent_steps": [{
                "agent": "syntax_gate",
                "status": "complete",
                "summary": result,
                "duration_ms": duration_ms
            }],
            "current_agent": "syntax_gate"
        }

    except Exception as exc:
        logger.exception("Syntax gate failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "syntax_gate", str(exc), duration_ms)
        await sse.publish_gate_result(run_id, "syntax_gate", "FAIL", f"Internal error: {exc}")
        
        return {
            "syntax_gate": "FAIL",
            "error_log": [f"syntax_gate error: {exc}"],
            "agent_steps": [{
                "agent": "syntax_gate",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "syntax_gate"
        }
