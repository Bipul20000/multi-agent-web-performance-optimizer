"""Report agent — builds final summary pushed to UI."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_mongo, get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the reporting phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()
    mongo = get_mongo()

    try:
        await sse.publish_agent_start(run_id, "report_agent", "Building final run report")

        fix_plan = state.get("fix_plan", {})
        psi_metrics = state.get("psi_metrics", {})
        production_psi_after = state.get("production_psi_after", {})
        deploy_status = state.get("deploy_status", "unknown")
        
        target_page = fix_plan.get("target_page", "/")
        target_metric = fix_plan.get("target_metric", "LCP")
        
        before_scores = psi_metrics.get(target_page, {}).get("mobile", {}).get("scores", {})
        if production_psi_after:
            after_scores = production_psi_after.get("mobile", {}).get("scores", {})
            metric_after_ms = production_psi_after.get("mobile", {}).get("core_web_vitals", {}).get(target_metric, {}).get("value", metric_before_ms)
        elif state.get("sandbox_psi"):
            after_scores = state.get("sandbox_psi", {}).get("scores", {})
            metric_after_ms = state.get("sandbox_psi", {}).get("core_web_vitals", {}).get(target_metric, {}).get("value", metric_before_ms)
        else:
            after_scores = before_scores
            metric_after_ms = metric_before_ms

        before_score = before_scores.get("performance", 0)
        after_score = after_scores.get("performance", before_score)
        score_delta = after_score - before_score

        metric_improved = metric_after_ms < metric_before_ms if metric_before_ms else False
        
        # 1. Compute ROI estimate
        lcp_improvement_ms = None
        if target_metric == "LCP" and metric_improved:
            lcp_improvement_ms = metric_before_ms - metric_after_ms
            conversion_lift_pct = round((lcp_improvement_ms / 100) * 0.8, 2)
            msg = f"{target_metric} improved by {lcp_improvement_ms}ms on {target_page}. Estimated conversion lift: ~{conversion_lift_pct}%"
        else:
            conversion_lift_pct = round(score_delta * 0.05, 2)
            msg = f"Performance score delta: {score_delta}. Estimated conversion lift: ~{conversion_lift_pct}%"
            
        roi_summary = {
            "score_before": before_score,
            "score_after": after_score,
            "scores_before": before_scores,
            "scores_after": after_scores,
            "score_delta": score_delta,
            "metric": target_metric,
            "improvement_ms": lcp_improvement_ms,
            "estimated_conversion_lift_pct": conversion_lift_pct,
            "message": msg
        }

        # 2. Build full run_summary dict
        run_summary = {
            "run_id": run_id,
            "website_url": state.get("website_url", "unknown"),
            "duration_ms": 0,  # Could compute total duration from agent_steps
            "target_page": target_page,
            "target_metric": target_metric,
            "fix_category": fix_plan.get("fix_category", "unknown"),
            "files_changed": [f.get("path") for f in state.get("generated_fixes", [])],
            "deploy_status": deploy_status,
            "pr_url": state.get("pr_url", ""),
            "auto_reverted": state.get("auto_reverted", False),
            "roi": roi_summary,
            "agent_steps": state.get("agent_steps", []),
            "risk_classification": state.get("risk_classification", "UNKNOWN"),
            "confidence_score": fix_plan.get("confidence_score", 0.0),
            "sandbox_psi": state.get("sandbox_psi", {}),
            "production_psi_after": production_psi_after,
            "psi_metrics": psi_metrics,
            "backend_metrics": state.get("backend_metrics", [])
        }
        
        # Compute total duration from agent steps
        total_duration = sum(step.get("duration_ms", 0) for step in run_summary["agent_steps"])
        run_summary["duration_ms"] = total_duration

        # 3. Publish run_complete SSE
        await sse.publish_run_complete(run_id, run_summary)

        # 4. Update MongoDB run with run_summary
        try:
            await mongo.update_run(run_id, {
                "run_summary": run_summary,
                "status": "complete"
            })
        except Exception as e:
            logger.warning(f"Failed to update MongoDB with run_summary: {e}")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_complete(run_id, "report_agent", "Final report generated", duration_ms)

        return {
            "agent_steps": [{
                "agent": "report_agent",
                "status": "complete",
                "summary": "Final report generated",
                "duration_ms": duration_ms
            }],
            "current_agent": "report_agent"
        }

    except Exception as exc:
        logger.exception("Report agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "report_agent", str(exc), duration_ms)
        
        return {
            "error_log": [f"report_agent error: {exc}"],
            "agent_steps": [{
                "agent": "report_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "report_agent"
        }
