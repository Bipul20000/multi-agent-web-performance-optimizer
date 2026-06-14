"""Risk classifier agent — pure rule-based classifier (no LLM)."""

from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_publisher


RISK_THRESHOLDS = {"HIGH": 55, "MEDIUM": 30}
IMPACT_THRESHOLDS = {"HIGH": 60, "MEDIUM": 35}

FIX_CATEGORY_RISK = {
    "image_optimization": 5,
    "font_loading": 8,
    "caching_headers": 10,
    "css_optimization": 12,
    "lazy_loading": 12,
    "add_attribute": 8,
    "third_party_removal": 25,
    "js_bundle_reduction": 20,
    "render_blocking": 20,
    "component_splitting": 25,
    "api_response_time": 15,
}

METRIC_WEIGHTS = {"LCP": 20, "TBT": 18, "CLS": 15, "FCP": 12, "SI": 8, "TTI": 6}
SONAR_RISK_SCORES = {"LOW": 0, "MED": 10, "HIGH": 20}
SHARED_UTIL_PATTERNS = ["utils/", "lib/", "helpers/", "hooks/", "context/", "store/"]


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute risk classification phase using pure deterministic rules."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        # STEP 1: Publish agent_start SSE
        await sse.publish_agent_start(
            run_id, "risk_classifier", "Classifying fix plan risk and impact"
        )

        # DEMO MODE: always proceed to show full pipeline
        from backend.config import get_settings
        demo_mode = get_settings().DEMO_MODE.lower() == "true"
        if demo_mode:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_gate_result(run_id, "risk_classifier", "LOW", "DEMO MODE: auto-approved")
            await sse.publish_agent_complete(run_id, "risk_classifier", "DEMO MODE: auto-approved", duration_ms)
            return {
                "risk_classification": "LOW",
                "confidence_score": 0.75,
                "agent_steps": [{
                    "agent": "risk_classifier",
                    "status": "complete", 
                    "summary": "DEMO MODE: auto-approved for full pipeline demonstration",
                    "duration_ms": duration_ms
                }],
                "current_agent": "risk_classifier"
            }

        # STEP 2: Guard clause
        fix_plan = state.get("fix_plan", {})
        if not fix_plan or not fix_plan.get("files_to_change"):
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_agent_complete(run_id, "risk_classifier", "Skipped: no fix plan", duration_ms)
            return {
                "risk_classification": "SKIP",
                "confidence_score": 0.0,
                "agent_steps": [{
                    "agent": "risk_classifier",
                    "status": "complete",
                    "summary": "Skipped: no fix plan or files to change",
                    "duration_ms": duration_ms,
                }],
                "current_agent": "risk_classifier",
            }

        # STEP 3: Compute IMPACT score (0-100)
        impact_score = 0
        
        # Factor 1: Business priority
        target_page = fix_plan.get("target_page", "")
        page_priority = state.get("business_priority", {}).get(target_page, {}).get("priority", 5)
        impact_score += page_priority * 3
        
        # Factor 2: Estimated PSI score delta
        score_delta = min(fix_plan.get("estimated_score_delta", 0), 30)
        impact_score += score_delta
        
        # Factor 3: Metric being fixed
        target_metric = fix_plan.get("target_metric", "")
        impact_score += METRIC_WEIGHTS.get(target_metric, 8)
        
        # Factor 4: Gemini confidence
        confidence = fix_plan.get("confidence_score", 0.5)
        impact_score += int(confidence * 20)
        
        impact_score = max(0, min(100, impact_score))
        
        if impact_score >= IMPACT_THRESHOLDS["HIGH"]:
            impact_level = "HIGH"
        elif impact_score >= IMPACT_THRESHOLDS["MEDIUM"]:
            impact_level = "MEDIUM"
        else:
            impact_level = "LOW"

        # STEP 4: Compute RISK score (0-100)
        risk_score = 0
        
        # Factor 1: Number of files being changed
        n_files = len(fix_plan.get("files_to_change", []))
        risk_score += min(n_files * 5, 20)
        
        # Factor 2: Fix category inherent risk
        fix_cat = fix_plan.get("fix_category", "")
        fix_cat_risk = FIX_CATEGORY_RISK.get(fix_cat, 15)
        risk_score += fix_cat_risk
        
        # Factor 3: Sonar risk
        sonar_risk = fix_plan.get("sonar_risk", "MED")
        risk_score += SONAR_RISK_SCORES.get(sonar_risk, 10)
        
        # Factor 4: Are any changed files shared utilities?
        changing_shared = any(
            any(pattern in f.get("path", "") for pattern in SHARED_UTIL_PATTERNS)
            for f in fix_plan.get("files_to_change", [])
        )
        if changing_shared:
            risk_score += 20
        
        # Factor 5: Previous failure for this exact fix_category on this stack
        stack_name = state.get("file_map", {}).get("stack", {}).get("framework", "")
        recent_failures = state.get("fix_memory", {}).get("recent_failures", [])
        has_previous_failure = any(
            f.get("fix_type") == fix_cat and f.get("stack", "").lower() in stack_name.lower()
            for f in recent_failures
        )
        if has_previous_failure:
            risk_score += 10
        
        risk_score = max(0, min(100, risk_score))
        
        if risk_score >= RISK_THRESHOLDS["HIGH"]:
            risk_level = "HIGH"
        elif risk_score >= RISK_THRESHOLDS["MEDIUM"]:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # STEP 5: Decision matrix → risk_classification
        if impact_score < 15 and risk_level == "HIGH":
            classification = "SKIP"
            recommended_action = "skip_run"
            reason = f"Low impact ({impact_score}/100) with high risk ({risk_score}/100). Not worth deploying."
        
        elif risk_level == "HIGH" or (risk_level == "MEDIUM" and confidence < 0.45):
            classification = "HIGH"
            recommended_action = "human_gate"
            reason = f"Risk score {risk_score}/100 requires human approval before deployment."
        
        elif impact_level == "LOW" and confidence < 0.15:
            classification = "SKIP"
            recommended_action = "skip_run"
            reason = f"Low confidence ({confidence:.2f}) on low-impact fix. Skipping this run."
        
        else:
            classification = risk_level  # LOW or MEDIUM
            recommended_action = "fix_generation"
            reason = f"Impact {impact_score}/100, Risk {risk_score}/100. Safe to auto-proceed."

        # STEP 6: Build detailed classification report
        classification_report = {
            "risk_classification": classification,
            "recommended_action": recommended_action,
            "impact_score": impact_score,
            "impact_level": impact_level,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "reason": reason,
            "factors": {
                "page_priority": page_priority,
                "estimated_score_delta": score_delta,
                "n_files_changed": n_files,
                "fix_category_risk": fix_cat_risk,
                "changing_shared_utils": changing_shared,
                "has_previous_failure": has_previous_failure,
                "confidence": confidence
            }
        }

        # STEP 7: Publish SSE gate_result
        await sse.publish_gate_result(
            run_id=run_id,
            gate_name="risk_classifier",
            result=classification,
            details=reason
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_complete(run_id, "risk_classifier", f"Classified as {classification}: {reason}", duration_ms)

        # STEP 8: Return state update
        return {
            "risk_classification": classification,
            "agent_steps": [{
                "agent": "risk_classifier",
                "status": "complete",
                "summary": reason,
                "classification": classification,
                "impact_score": impact_score,
                "risk_score": risk_score,
                "duration_ms": duration_ms
            }],
            "current_agent": "risk_classifier",
            "fix_plan": {**fix_plan, "_risk_report": classification_report}
        }

    except Exception as exc:
        logger.exception("Risk classifier failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "risk_classifier", str(exc), duration_ms)
        
        return {
            "risk_classification": "SKIP",
            "error_log": [f"risk_classifier error: {exc}"],
            "agent_steps": [{
                "agent": "risk_classifier",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "risk_classifier"
        }
