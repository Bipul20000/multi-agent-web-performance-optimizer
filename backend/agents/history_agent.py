"""History agent — loads run history and fix memory."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_mongo, get_publisher


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute history and trend analysis phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    
    sse = get_publisher()
    mongo = get_mongo()

    try:
        await sse.publish_agent_start(run_id, "history_agent", "Loading run history and fix memory")

        # STEP 2 — Load recent runs
        raw_runs = await mongo.get_recent_runs(client_id=state.get("client_id"), limit=10)
        
        recent_runs = []
        for r in raw_runs:
            recent_runs.append({
                "run_id": r.get("run_id"),
                "timestamp": r.get("start_time"),
                "website_url": r.get("website_url"),
                "best_page_improved": r.get("best_page_improved"),
                "metric_improved": r.get("metric_improved"),
                "score_delta": r.get("score_delta"),
                "fix_type": r.get("fix_type"),
                "success": r.get("success"),
                "deploy_status": r.get("deploy_status")
            })

        # STEP 3 — Load fix memory
        framework = state.get("file_map", {}).get("framework")
        raw_memory = await mongo.get_fix_memory(stack=framework, limit=20)
        
        proven_successes = []
        recent_failures = []
        risky_fixes = []
        
        lcp_fixes = {}
        cls_fixes = {}
        tbt_fixes = {}
        
        for mem in raw_memory:
            fix_type = mem.get("fix_type", "")
            metric = mem.get("metric_targeted", "")
            is_success = mem.get("success", False)
            side_effects = mem.get("side_effects", [])
            delta = mem.get("after", 0) - mem.get("before", 0)
            
            if is_success and delta > 5:
                proven_successes.append(mem)
                
            if not is_success:
                recent_failures.append(mem)
                
            if side_effects:
                risky_fixes.append(mem)
                
            if is_success:
                if metric == "LCP": lcp_fixes[fix_type] = lcp_fixes.get(fix_type, 0) + delta
                if metric == "CLS": cls_fixes[fix_type] = cls_fixes.get(fix_type, 0) + delta
                if metric == "TBT": tbt_fixes[fix_type] = tbt_fixes.get(fix_type, 0) + delta
                
        best_fix_for_lcp = max(lcp_fixes.items(), key=lambda x: x[1])[0] if lcp_fixes else None
        best_fix_for_cls = max(cls_fixes.items(), key=lambda x: x[1])[0] if cls_fixes else None
        best_fix_for_tbt = max(tbt_fixes.items(), key=lambda x: x[1])[0] if tbt_fixes else None
        
        fix_memory = {
            "proven_successes": proven_successes,
            "recent_failures": recent_failures,
            "risky_fixes": risky_fixes,
            "best_fix_for_lcp": best_fix_for_lcp,
            "best_fix_for_cls": best_fix_for_cls,
            "best_fix_for_tbt": best_fix_for_tbt
        }

        # STEP 4 — Compute trend analysis
        trend_analysis = {"performance_trend": "insufficient_data"}
        
        if len(recent_runs) >= 3:
            successful_runs = [r for r in recent_runs if r.get("success")]
            total_fixes = len([r for r in recent_runs if r.get("fix_type")])
            successes = len(successful_runs)
            
            # Very simple trend: check if last 3 runs have positive delta
            last_3_deltas = [r.get("score_delta", 0) or 0 for r in recent_runs[:3]]
            if all(d > 0 for d in last_3_deltas): trend = "improving"
            elif all(d < 0 for d in last_3_deltas): trend = "degrading"
            else: trend = "stable"
            
            trend_analysis = {
                "performance_trend": trend,
                "last_known_good_score": None, # Complex to compute here accurately
                "days_since_improvement": 0,
                "total_fixes_deployed": total_fixes,
                "total_fixes_successful": successes,
                "success_rate": round(successes / max(1, total_fixes), 2)
            }

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary = f"Loaded {len(recent_runs)} runs, {len(raw_memory)} fix memories. Trend: {trend_analysis['performance_trend']}"
        
        await sse.publish_agent_complete(run_id, "history_agent", summary, duration_ms)

        # STEP 5 — Return state
        return {
            "recent_runs": recent_runs,
            "fix_memory": fix_memory,
            "agent_steps": [{
                "agent": "history_agent",
                "status": "complete",
                "summary": summary,
                "duration_ms": duration_ms
            }],
            "current_agent": "history_agent"
        }

    except Exception as exc:
        logger.exception("History agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "history_agent", str(exc), duration_ms)
        
        return {
            "recent_runs": [],
            "fix_memory": {},
            "error_log": [f"history_agent error: {exc}"],
            "agent_steps": [{
                "agent": "history_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "history_agent"
        }
