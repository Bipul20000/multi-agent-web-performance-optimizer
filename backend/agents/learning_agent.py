"""Learning agent — saves run outcome to MongoDB to improve future runs."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_mongo, get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the learning phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()
    mongo = get_mongo()

    try:
        await sse.publish_agent_start(run_id, "learning_agent", "Saving run outcomes to memory")

        fix_plan = state.get("fix_plan", {})
        file_map = state.get("file_map", {})
        psi_metrics = state.get("psi_metrics", {})
        production_psi_after = state.get("production_psi_after", {})
        deploy_status = state.get("deploy_status", "unknown")
        auto_reverted = state.get("auto_reverted", False)
        
        target_page = fix_plan.get("target_page", "/")
        target_metric = fix_plan.get("target_metric", "LCP")
        
        before_score = psi_metrics.get(target_page, {}).get("mobile", {}).get("scores", {}).get("performance", 0)
        after_score = production_psi_after.get("scores", {}).get("performance", before_score)
        
        success = deploy_status in ("deployed", "deployed_supervised") and not auto_reverted
        
        # Determine actual metric after if available
        metric_after_ms = 0
        if production_psi_after:
            metric_after_ms = production_psi_after.get("mobile", {}).get("core_web_vitals", {}).get(target_metric, {}).get("value", 0)
            
        business_priority = state.get("business_priority", {})
        page_type = business_priority.get(target_page, {}).get("type", "unknown")
        
        # 1. Build fix_memory entry
        entry = {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fix_type": fix_plan.get("fix_category", "unknown"),
            "stack": file_map.get("stack", {}).get("framework", "unknown"),
            "metric_targeted": target_metric,
            "before": before_score,
            "after": after_score,
            "metric_before_ms": fix_plan.get("estimated_improvement", {}).get("before_ms", 0),
            "metric_after_ms": metric_after_ms,
            "success": success,
            "side_effects": [],
            "page_type": page_type,
            "files_changed": [f.get("path") for f in state.get("generated_fixes", [])],
            "confidence_was": fix_plan.get("confidence_score", 0.0),
            "risk_was": state.get("risk_classification", "UNKNOWN"),
            "reverted": auto_reverted
        }

        # 2. Detect side effects
        side_effects = []
        if production_psi_after:
            before_cwv = psi_metrics.get(target_page, {}).get("mobile", {}).get("core_web_vitals", {})
            after_cwv = production_psi_after.get("mobile", {}).get("core_web_vitals", {})
            
            for metric, before_data in before_cwv.items():
                before_val = before_data.get("value", 0)
                after_val = after_cwv.get(metric, {}).get("value", 0)
                
                # Check if metric got significantly worse (e.g., > 5% regression)
                if before_val > 0 and after_val > before_val * 1.05:
                    side_effects.append(f"{metric} degraded: {before_val} -> {after_val}")
                    
        entry["side_effects"] = side_effects

        # 3. Save to MongoDB
        try:
            await mongo.save_fix_memory(entry)
        except Exception as e:
            logger.warning(f"Failed to save fix memory: {e}")

        # 4. Update baseline if improved
        baseline = state.get("baseline_scores", {}).get(target_page, {}).get("scores", {}).get("performance", 0)
        if success and after_score > baseline:
            try:
                website_url = state.get("website_url", "").rstrip("/")
                full_url = website_url + target_page
                await mongo.save_baseline(full_url, {"performance": after_score})
                logger.info(f"Updated baseline for {full_url} to {after_score}")
            except Exception as e:
                logger.warning(f"Failed to update baseline: {e}")

        # 5. Update run document
        now = datetime.now(timezone.utc).isoformat()
        try:
            await mongo.update_run(run_id, {
                "status": "complete",
                "deploy_status": deploy_status,
                "end_time": now,
                "final_score": after_score,
                "auto_reverted": auto_reverted
            })
        except Exception as e:
            logger.warning(f"Failed to update run document: {e}")

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary = "Run outcomes saved to memory"
        await sse.publish_agent_complete(run_id, "learning_agent", summary, duration_ms)

        return {
            "agent_steps": [{
                "agent": "learning_agent",
                "status": "complete",
                "summary": summary,
                "duration_ms": duration_ms
            }],
            "current_agent": "learning_agent"
        }

    except Exception as exc:
        logger.exception("Learning agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "learning_agent", str(exc), duration_ms)
        
        return {
            "error_log": [f"learning_agent error: {exc}"],
            "agent_steps": [{
                "agent": "learning_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "learning_agent"
        }
