"""Context agent — establishes business priority and urgency."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_publisher

PRIORITY_RULES = {
    r"/(checkout|cart|buy|order)": (10, "conversion", True),
    r"/(pricing|plans|upgrade)":   (9,  "conversion", True),
    r"/(book|booking|schedule)":   (9,  "conversion", True),
    r"/(demo|trial|signup|register)": (8, "acquisition", True),
    r"/(product|shop|store)":      (8,  "product",    True),
    r"/(contact|get-in-touch)":    (7,  "lead_gen",   True),
    r"/(home|^/$)":                (7,  "awareness",  False),
    r"/(about|team|company)":      (4,  "info",       False),
    r"/(blog|news|press)":         (3,  "content",    False),
    r"/(careers|jobs)":            (2,  "hr",         False),
    r"/(privacy|terms|legal)":     (1,  "legal",      False),
}


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute business context establishment phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "context_agent", "Establishing business context and priority")

        # STEP 2 — Build page priority map
        business_priority = {}
        
        env_config = os.getenv("BUSINESS_PRIORITY_CONFIG")
        if env_config:
            try:
                business_priority = json.loads(env_config)
            except Exception as e:
                logger.warning(f"Failed to parse BUSINESS_PRIORITY_CONFIG: {e}")
                
        psi_metrics = state.get("psi_metrics", {})
        
        for path in psi_metrics.keys():
            if path in business_priority: continue
            
            # Infer priority
            priority = 5
            page_type = "unknown"
            revenue_critical = False
            
            for pattern, (p, pt, rc) in PRIORITY_RULES.items():
                if re.search(pattern, path):
                    priority = p
                    page_type = pt
                    revenue_critical = rc
                    break
                    
            business_priority[path] = {
                "priority": priority,
                "type": page_type,
                "revenue_critical": revenue_critical
            }

        # STEP 3 — Determine peak traffic windows
        peak_config = os.getenv("PEAK_HOURS")
        if peak_config:
            try:
                windows = json.loads(peak_config)
            except:
                windows = [{"start": "09:00", "end": "11:00"}, {"start": "19:00", "end": "22:00"}]
        else:
            windows = [{"start": "09:00", "end": "11:00"}, {"start": "19:00", "end": "22:00"}]
            
        now = datetime.now(timezone.utc)
        current_time_str = now.strftime("%H:%M")
        
        is_peak_traffic = False
        for window in windows:
            if window["start"] <= current_time_str <= window["end"]:
                is_peak_traffic = True
                break

        # STEP 4 — Compute priority-weighted performance gap
        ranked_pages = []
        top_priority_page = ""
        highest_urgency = -1.0
        
        for path, data in psi_metrics.items():
            info = business_priority.get(path, {"priority": 5})
            perf_score = data.get("mobile", {}).get("scores", {}).get("performance", 100.0)
            gap = 100.0 - perf_score
            urgency = info["priority"] * gap
            
            business_priority[path]["weighted_urgency"] = urgency
            
            ranked_pages.append({
                "path": path,
                "priority": info["priority"],
                "type": info.get("type", "unknown"),
                "revenue_critical": info.get("revenue_critical", False),
                "perf_score": perf_score,
                "gap": gap,
                "weighted_urgency": urgency
            })
            
            if urgency > highest_urgency:
                highest_urgency = urgency
                top_priority_page = path
                
        ranked_pages.sort(key=lambda x: x["weighted_urgency"], reverse=True)
        
        recommendation = "No pages to optimize."
        if ranked_pages:
            top = ranked_pages[0]
            recommendation = f"Focus on {top['path']} (priority {top['priority']}, score {top['perf_score']}/100, gap {top['gap']:.1f}pts)"

        # Publish metric update
        await sse.publish_metric_update(run_id, "context_agent", {
            "top_priority_page": top_priority_page,
            "recommendation": recommendation,
            "is_peak_traffic": is_peak_traffic
        })

        duration_ms = int((time.monotonic() - start_time) * 1000)
        
        await sse.publish_agent_complete(run_id, "context_agent", recommendation, duration_ms)

        # STEP 5 — Return state
        return {
            "business_priority": business_priority,
            "agent_steps": [{
                "agent": "context_agent",
                "status": "complete",
                "summary": recommendation,
                "duration_ms": duration_ms
            }],
            "current_agent": "context_agent"
        }

    except Exception as exc:
        logger.exception("Context agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "context_agent", str(exc), duration_ms)
        
        return {
            "business_priority": {},
            "error_log": [f"context_agent error: {exc}"],
            "agent_steps": [{
                "agent": "context_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "context_agent"
        }
