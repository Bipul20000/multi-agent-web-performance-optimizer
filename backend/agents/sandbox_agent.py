"""Sandbox agent — tests generated code in a Vercel preview environment."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from backend.config import get_settings
from backend.state import PipelineState
from backend.utils.psi_client import run_psi
from backend.utils.shared import get_github, get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the sandbox validation phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "sandbox_agent", "Testing fixes in sandbox environment")

        fixes = state.get("generated_fixes", [])
        if not fixes:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "sandbox_gate", "APPROVE", "No fixes to test")
            await sse.publish_agent_complete(run_id, "sandbox_agent", "APPROVE (no fixes)", duration_ms)
            return {
                "sandbox_gate": "APPROVE",
                "agent_steps": [{
                    "agent": "sandbox_agent",
                    "status": "complete",
                    "summary": "Passed (no fixes)",
                    "duration_ms": duration_ms
                }],
                "current_agent": "sandbox_agent"
            }

        gh = get_github()
        
        # 1. Create a temp branch
        branch_name = f"awpis/fix-{run_id[:8]}"
        default_branch = await gh.get_default_branch()
        try:
            await gh.create_branch(branch_name, from_branch=default_branch)
        except Exception as e:
            logger.warning(f"Branch {branch_name} might already exist or creation failed: {e}")

        # 2. Push all generated_fixes
        file_contents = state.get("file_map", {}).get("file_contents", {})
        for fix in fixes:
            path = fix.get("path", "")
            content = fix.get("new_content", "")
            
            # Find sha if available
            sha = None
            if path in file_contents:
                try:
                    res = await gh.get_file_content(path, default_branch)
                    sha = res.get("sha")
                except Exception:
                    pass
            
            if not sha:
                try:
                    res = await gh.get_file_content(path, default_branch)
                    sha = res.get("sha")
                except Exception:
                    pass # File might be new

            await gh.create_or_update_file(
                path=path,
                content=content,
                message=f"[AWPIS] Update {path}",
                branch=branch_name,
                sha=sha
            )

        # 3. Wait for Vercel preview to build
        await sse.publish_metric_update(run_id, "sandbox_agent", {"status": "Waiting for Vercel preview deployment..."})
        
        preview_url = None
        for _ in range(12):  # 120s max (12 * 10s)
            await asyncio.sleep(10)
            try:
                # Raw API call to deployments
                deployments = await gh._get(f"/repos/{gh._repo}/deployments?ref={branch_name}&environment=Preview")
                if deployments:
                    deployment_id = deployments[0].get("id")
                    statuses = await gh._get(f"/repos/{gh._repo}/deployments/{deployment_id}/statuses")
                    
                    if statuses:
                        latest = statuses[0]
                        if latest.get("state") == "success":
                            preview_url = latest.get("environment_url")
                            break
                        elif latest.get("state") in ("error", "failure"):
                            raise Exception("Deployment failed")
            except Exception as e:
                logger.debug(f"Deployment polling error: {e}")

        if not preview_url:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            reason = "preview_timeout"
            await sse.publish_gate_result(run_id, "sandbox_gate", "REJECT", reason)
            await sse.publish_agent_complete(run_id, "sandbox_agent", "REJECT (Preview timeout)", duration_ms)
            return {
                "sandbox_gate": "REJECT",
                "sandbox_url": None,
                "sandbox_psi": {},
                "agent_steps": [{
                    "agent": "sandbox_agent",
                    "status": "complete",
                    "summary": reason,
                    "duration_ms": duration_ms
                }],
                "current_agent": "sandbox_agent"
            }

        # 4. Run PSI on preview URL
        target_page = state.get("fix_plan", {}).get("target_page", "/")
        full_url = preview_url.rstrip("/") + "/" + target_page.lstrip("/")
        
        api_key = get_settings().PSI_API_KEY
        await sse.publish_metric_update(run_id, "sandbox_agent", {"status": f"Running PSI on {full_url}"})
        
        try:
            preview_psi = await run_psi(full_url, api_key, strategy="mobile")
        except Exception as e:
            logger.error(f"PSI failed on preview: {e}")
            preview_psi = {"scores": {"performance": 0}}

        # 5. Compare against baseline
        baseline_score = state.get("baseline_scores", {}).get(target_page, {}).get("scores", {}).get("performance", 0.0)
        current_score = state.get("psi_metrics", {}).get(target_page, {}).get("mobile", {}).get("scores", {}).get("performance", 0.0)
        preview_score = preview_psi.get("scores", {}).get("performance", 0.0)
        
        if preview_score > current_score:
            gate_result = "APPROVE"
            reason = f"Performance improved from {current_score} to {preview_score}"
        elif preview_score <= current_score or preview_score < baseline_score - 5:
            gate_result = "REJECT"
            reason = f"Performance degraded or stalled: {current_score} -> {preview_score}"
        else:
            gate_result = "REJECT"
            reason = "No improvement measured"

        # 6. Branch cleanup on reject
        if gate_result == "REJECT":
            try:
                await gh._request("DELETE", f"/repos/{gh._repo}/git/refs/heads/{branch_name}")
                logger.info(f"Deleted rejected branch {branch_name}")
            except Exception as e:
                logger.warning(f"Failed to delete branch {branch_name}: {e}")

        updated_fix_plan = dict(state.get("fix_plan", {}))
        updated_fix_plan["sandbox_branch"] = branch_name

        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_gate_result(run_id, "sandbox_gate", gate_result, reason)
        await sse.publish_agent_complete(run_id, "sandbox_agent", f"{gate_result}: {reason}", duration_ms)

        return {
            "sandbox_gate": gate_result,
            "sandbox_url": preview_url,
            "sandbox_psi": preview_psi,
            "fix_plan": updated_fix_plan,
            "agent_steps": [{
                "agent": "sandbox_agent",
                "status": "complete",
                "summary": reason,
                "duration_ms": duration_ms
            }],
            "current_agent": "sandbox_agent"
        }

    except Exception as exc:
        logger.exception("Sandbox agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "sandbox_agent", str(exc), duration_ms)
        await sse.publish_gate_result(run_id, "sandbox_gate", "REJECT", f"Internal error: {exc}")
        
        return {
            "sandbox_gate": "REJECT",
            "error_log": [f"sandbox_agent error: {exc}"],
            "agent_steps": [{
                "agent": "sandbox_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "sandbox_agent"
        }
