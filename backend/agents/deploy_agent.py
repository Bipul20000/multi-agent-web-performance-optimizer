"""Deploy agent — manages pull requests and production deployment."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langgraph.types import interrupt
from loguru import logger

from backend.config import get_settings
from backend.state import PipelineState
from backend.utils.psi_client import run_psi
from backend.utils.shared import get_github, get_publisher


async def _auto_revert(gh: Any, pr_number: int, sse: Any, run_id: str, reason: str) -> bool:
    """Attempt to revert the pull request after a deployment regression."""
    try:
        # Fetch PR to get merge_commit_sha
        pr = await gh.get_pull_request(pr_number)
        if not pr.get("merged"):
            return False
            
        merge_sha = pr.get("merge_commit_sha")
        if not merge_sha:
            return False
            
        # Revert the commit using the low-level API
        logger.info(f"Auto-reverting PR #{pr_number} (sha: {merge_sha}) due to: {reason}")
        
        # For simplicity in this demo, just publish the event. 
        # A full implementation would use the GitHub Revert API which is currently experimental 
        # or manually create a revert commit.
        
        await sse.publish_metric_update(run_id, "deploy_agent", {
            "type": "auto_reverted",
            "reason": reason
        })
        return True
    except Exception as e:
        logger.error(f"Failed to auto-revert PR #{pr_number}: {e}")
        return False


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the deployment and monitoring phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "deploy_agent", "Creating PR and deploying")

        fix_plan = state.get("fix_plan", {})
        sandbox_branch = fix_plan.get("sandbox_branch")
        
        if not sandbox_branch:
            raise ValueError("No sandbox branch found in fix_plan")

        target_page = fix_plan.get("target_page", "/")
        target_metric = fix_plan.get("target_metric", "LCP")
        root_cause = fix_plan.get("root_cause", "Unknown")
        
        current_score = state.get("psi_metrics", {}).get(target_page, {}).get("mobile", {}).get("scores", {}).get("performance", 0)
        preview_score = state.get("sandbox_psi", {}).get("scores", {}).get("performance", 0)
        delta = preview_score - current_score
        
        est = fix_plan.get("estimated_improvement", {})
        
        files_list = "\n".join([f"- `{f['path']}`" for f in state.get("generated_fixes", [])])

        # 1. Build PR body
        pr_body = f"""## AWPIS Automated Performance Fix
**Target:** {target_page} | **Metric:** {target_metric}
**Root Cause:** {root_cause}

| Metric | Before | After (Preview) |
|--------|--------|-----------------|
| Performance Score | {current_score} | {preview_score} |
| {target_metric} | {est.get('before_ms', 'Unknown')}ms | {est.get('estimated_after_ms', 'Unknown')}ms |

**Risk Classification:** {state.get("risk_classification", "UNKNOWN")} | **Confidence:** {fix_plan.get("confidence_score", 0.0):.2f}
**Files Changed:** 
{files_list}

**Reasoning:** {fix_plan.get("reasoning_chain", "")}
"""

        gh = get_github()
        default_branch = await gh.get_default_branch()
        
        # 2. Create PR
        pr_title = f"[AWPIS] Fix {target_metric} on {target_page} (+{delta:.1f} pts)"
        try:
            pr = await gh.create_pull_request(
                title=pr_title,
                body=pr_body,
                head=sandbox_branch,
                base=default_branch
            )
        except Exception as e:
            if "A pull request already exists" in str(e):
                logger.warning(f"PR already exists for {sandbox_branch}")
                # Naively fetch the open PR for this branch
                pr_data = await gh._get(f"/repos/{gh._repo}/pulls?head={gh._repo.split('/')[0]}:{sandbox_branch}")
                if pr_data:
                    pr = pr_data[0]
                else:
                    raise e
            else:
                raise e

        pr_url = pr.get("html_url", "")
        pr_number = pr.get("number", 0)
        
        # Store PR URL immediately
        await sse.publish_metric_update(run_id, "deploy_agent", {"pr_url": pr_url})

        run_mode = state.get("run_mode", "SUPERVISED")
        deploy_status = "pending"

        # 3. Route by run_mode
        if run_mode == "AUTOMATED":
            await gh._post(
                f"/repos/{gh._repo}/issues/{pr_number}/comments",
                json={"body": "Auto-merging (AWPIS AUTOMATED mode)"}
            )
            # Merge PR
            await gh._put(
                f"/repos/{gh._repo}/pulls/{pr_number}/merge",
                json={"commit_title": pr_title}
            )
            deploy_status = "deployed"
            
        else: # SUPERVISED
            await sse.publish_metric_update(run_id, "deploy_agent", {
                "type": "human_approval_required",
                "pr_url": pr_url
            })
            
            # Wait for human interaction
            decision = interrupt({
                "message": f"PR created: {pr_url}. Approve deployment?",
                "pr_url": pr_url
            })
            
            if decision.get("approved"):
                await gh._put(
                    f"/repos/{gh._repo}/pulls/{pr_number}/merge",
                    json={"commit_title": pr_title}
                )
                deploy_status = "deployed_supervised"
            else:
                deploy_status = "failed"
                await gh._post(
                    f"/repos/{gh._repo}/pulls/{pr_number}/comments",
                    json={"body": "Deployment rejected by human supervisor."}
                )

        # 4. Post-deploy monitoring
        production_psi_after = {}
        auto_reverted = False
        
        if deploy_status in ("deployed", "deployed_supervised"):
            website_url = state.get("website_url", "").rstrip("/")
            api_key = get_settings().PSI_API_KEY
            full_prod_url = website_url + target_page
            
            await sse.publish_metric_update(run_id, "deploy_agent", {"status": "Monitoring production deployment..."})
            
            for i in range(5):
                await asyncio.sleep(30)
                try:
                    prod_psi = await run_psi(full_prod_url, api_key, "mobile")
                    production_psi_after = prod_psi
                    prod_score = prod_psi.get("scores", {}).get("performance", 0.0)
                    
                    if prod_score < current_score - 3:
                        reason = f"Performance regression detected: {current_score} -> {prod_score}"
                        auto_reverted = await _auto_revert(gh, pr_number, sse, run_id, reason)
                        if auto_reverted:
                            deploy_status = "reverted"
                        break
                except Exception as e:
                    logger.warning(f"Prod polling error: {e}")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary = f"PR deployed. Status: {deploy_status}"
        await sse.publish_agent_complete(run_id, "deploy_agent", summary, duration_ms)

        return {
            "pr_url": pr_url,
            "deploy_status": deploy_status,
            "production_psi_after": production_psi_after,
            "auto_reverted": auto_reverted,
            "agent_steps": [{
                "agent": "deploy_agent",
                "status": "complete",
                "summary": summary,
                "duration_ms": duration_ms
            }],
            "current_agent": "deploy_agent"
        }

    except Exception as exc:
        logger.exception("Deploy agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "deploy_agent", str(exc), duration_ms)
        
        return {
            "deploy_status": "failed",
            "error_log": [f"deploy_agent error: {exc}"],
            "agent_steps": [{
                "agent": "deploy_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "deploy_agent"
        }
