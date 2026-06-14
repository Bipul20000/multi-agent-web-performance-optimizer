"""Reasoning agent — produces a structured fix plan using Gemini."""

from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.gemini_client import call_with_structured_output, get_groq_reasoning_model
from backend.utils.shared import get_publisher
from backend.config import get_settings


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the reasoning phase to generate a fix plan."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        # STEP 1: Publish agent_start SSE
        await sse.publish_agent_start(
            run_id, "reasoning_agent", "Analyzing data to generate fix plan"
        )

        # STEP 2: Guard clause
        psi = state.get("psi_metrics", {})
        if not psi:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_agent_complete(run_id, "reasoning_agent", "Skipped: no metrics", duration_ms)
            return {
                "fix_plan": {},
                "confidence_score": 0.0,
                "deploy_status": "no_metrics",
                "agent_steps": [{
                    "agent": "reasoning_agent",
                    "status": "complete",
                    "summary": "Skipped: no PSI metrics",
                    "duration_ms": duration_ms,
                }],
                "current_agent": "reasoning_agent",
            }

        file_map = state.get("file_map", {})
        if not file_map or not file_map.get("file_contents"):
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_agent_complete(run_id, "reasoning_agent", "Skipped: no codebase", duration_ms)
            return {
                "fix_plan": {},
                "confidence_score": 0.1,
                "deploy_status": "no_codebase",
                "agent_steps": [{
                    "agent": "reasoning_agent",
                    "status": "complete",
                    "summary": "Skipped: no codebase contents",
                    "duration_ms": duration_ms,
                }],
                "current_agent": "reasoning_agent",
            }

        # STEP 3: Select the target page using business-weighted logic
        ranked = state.get("business_priority", {})
        target_page = None

        for page_path in sorted(
            ranked, key=lambda p: ranked[p].get("weighted_urgency", 0), reverse=True
        ):
            if page_path in psi:
                mobile_cwv = psi[page_path].get("mobile", {}).get("core_web_vitals", {})
                has_poor_metric = any(
                    v.get("rating") in ("poor", "needs-improvement")
                    for v in mobile_cwv.values()
                )
                if has_poor_metric:
                    target_page = page_path
                    break

        if not target_page:
            target_page = list(psi.keys())[0]

        # Find worst metric on target page
        mobile_cwv = psi[target_page]["mobile"]["core_web_vitals"]
        metric_priority = ["LCP", "TBT", "CLS", "FCP", "SI", "TTI"]
        target_metric = "LCP"

        for m in metric_priority:
            if m in mobile_cwv and mobile_cwv[m].get("rating") == "poor":
                target_metric = m
                break
        else:
            for m in metric_priority:
                if m in mobile_cwv and mobile_cwv[m].get("rating") == "needs-improvement":
                    target_metric = m
                    break

        # STEP 4: Build rich context payload for Gemini
        current_val = mobile_cwv.get(target_metric, {}).get("value", 0)
        current_rating = mobile_cwv.get(target_metric, {}).get("rating", "unknown")
        perf_score = psi[target_page]["mobile"]["scores"]["performance"]

        context_summary = {
            "target": {
                "page": target_page,
                "metric": target_metric,
                "current_value": current_val,
                "current_rating": current_rating,
                "perf_score": perf_score,
                "business_priority": ranked.get(target_page, {}).get("priority", 5),
                "revenue_critical": ranked.get(target_page, {}).get("revenue_critical", False),
                "weighted_urgency": ranked.get(target_page, {}).get("weighted_urgency", 0),
            },
            "opportunities": psi[target_page]["mobile"].get("opportunities", [])[:3],
            "stack": file_map.get("stack", {}),
            "performance_red_flags": file_map.get("performance_patterns", {}).get("red_flags", {}),
            "good_patterns_present": file_map.get("performance_patterns", {}).get("good_patterns", {}),
            "available_files": state.get("relevant_files", [])[:20],
            "forbidden_files": state.get("forbidden_files", []),
            "fix_memory_summary": {
                "proven_successes": state.get("fix_memory", {}).get("proven_successes", [])[:2],
                "recent_failures": state.get("fix_memory", {}).get("recent_failures", [])[:2],
                "best_for_target_metric": state.get("fix_memory", {}).get(f"best_fix_for_{target_metric.lower()}", None),
            },
            "recent_commits": file_map.get("recent_commits", [])[:1],
        }

        # STEP 5: Build the SYSTEM PROMPT
        SYSTEM_PROMPT = """
        You are the Reasoning Agent for AWPIS (Autonomous Web Performance Intelligence System).
        
        Your role: Analyze web performance data, codebase structure, and fix history to produce
        a precise, actionable FIX PLAN that will improve Core Web Vitals scores.
        
        You have deep expertise in:
        - Core Web Vitals (LCP, CLS, TBT, FCP) and their root causes
        - Next.js / React performance optimization patterns
        - Safe vs risky code changes in production systems
        - Understanding which PSI opportunities map to which code changes
        
        Constraints you MUST follow:
        1. Only suggest changes to files that exist in available_files
        2. Never suggest changes to forbidden_files
        3. Never suggest changes to authentication, payment, or database files
        4. Prefer targeted, minimal changes over sweeping refactors
        5. If fix_memory shows this approach failed before on this stack — suggest a different approach
        6. Your confidence_score must be HONEST — low confidence is better than overconfident wrong plans
        
        Think step by step before producing your final JSON answer.
        """

        # File preview logic
        top_5_files = list(file_map.get("file_contents", {}).items())[:5]
        context_summary["file_contents_preview"] = {
            path: content[:150]
            for path, content in top_5_files
        }

        def build_user_prompt(preview_dict: dict) -> str:
            return f"""
            ## Performance Context
            
            Target Page: {context_summary['target']['page']}
            Target Metric: {context_summary['target']['metric']} = {context_summary['target']['current_value']}ms 
              ({context_summary['target']['current_rating']})
            Overall Performance Score: {context_summary['target']['perf_score']}/100
            Business Priority: {context_summary['target']['business_priority']}/10
            Revenue Critical: {context_summary['target']['revenue_critical']}
            
            ## PSI Opportunities (what Google's auditor flagged)
            {json.dumps(context_summary['opportunities'], indent=2)}
            
            ## Tech Stack
            {json.dumps(context_summary['stack'], indent=2)}
            
            ## Performance Red Flags Found in Code
            {json.dumps(context_summary['performance_red_flags'], indent=2)}
            
            ## Good Patterns Already Present
            {json.dumps(context_summary['good_patterns_present'], indent=2)}
            
            ## Available Files (you can only change these)
            {json.dumps(context_summary['available_files'], indent=2)}
            
            ## File Content Previews
            {json.dumps(preview_dict, indent=2)}
            
            ## Files You Must NOT Touch
            {json.dumps(context_summary['forbidden_files'], indent=2)}
            
            ## Fix History (what was tried before)
            {json.dumps(context_summary['fix_memory_summary'], indent=2)}
            
            ## Recent Code Changes (could have caused regression)
            {json.dumps(context_summary['recent_commits'], indent=2)}
            
            ## Your Task
            
            Analyze all of the above. Think through:
            1. What is the most likely ROOT CAUSE of the {target_metric} issue given the code patterns?
            2. Which specific file(s) should be changed to fix it?
            3. What exact change should be made? Be specific — not "optimize images" but 
               "replace <img> tags in components/Hero.jsx with next/image with width=1200, height=600"
            4. What is the risk level? Consider: is this a shared component? Does changing it affect many pages?
            5. How confident are you? Be honest — if the file contents don't show the root cause clearly, 
               lower your confidence.
            
            Then produce your FIX PLAN as JSON.
            """

        USER_PROMPT = build_user_prompt(context_summary["file_contents_preview"])
        full_prompt = SYSTEM_PROMPT + USER_PROMPT
        if len(full_prompt) > 20000:
            logger.warning("Prompt exceeds 20k tokens. Emergency cut: removing file_contents_preview.")
            USER_PROMPT = build_user_prompt({})

        # STEP 7: Call Gemini
        model = get_groq_reasoning_model(get_settings().GROQ_API_KEY)
        
        FIX_PLAN_SCHEMA = {
            "type": "object",
            "properties": {
                "target_metric": {"type": "string", "description": "which CWV metric this fix targets (LCP/CLS/TBT/FCP)"},
                "target_page": {"type": "string", "description": "page path being fixed"},
                "root_cause": {"type": "string", "description": "plain English explanation of why the metric is poor"},
                "root_cause_evidence": {"type": "string", "description": "which specific code or PSI audit proves this"},
                "fix_category": {
                    "type": "string",
                    "description": "one of: image_optimization|font_loading|js_bundle_reduction|css_optimization|lazy_loading|caching_headers|api_response_time|third_party_removal|render_blocking|component_splitting"
                },
                "fix_description": {"type": "string", "description": "plain English description of the exact change"},
                "files_to_change": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "exact file path"},
                            "change_type": {"type": "string", "description": "modify|add_config|add_attribute"},
                            "specific_change": {"type": "string", "description": "exact description of what to change in this file (line-level specificity)"},
                            "why": {"type": "string", "description": "why this file change fixes the root cause"}
                        },
                        "required": ["path", "change_type", "specific_change", "why"]
                    }
                },
                "files_to_NOT_touch": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "list of file paths that should not be modified"
                },
                "estimated_improvement": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": "string"},
                        "before_ms": {"type": "number"},
                        "estimated_after_ms": {"type": "number"},
                        "confidence": {"type": "string", "description": "low|medium|high"}
                    },
                    "required": ["metric", "before_ms", "estimated_after_ms", "confidence"]
                },
                "estimated_score_delta": {"type": "number", "description": "estimated PSI score improvement (0-20 range is realistic)"},
                "sonar_risk": {"type": "string", "description": "LOW|MED|HIGH based on complexity of change"},
                "confidence_score": {"type": "number", "description": "0.0 to 1.0 (be honest)"},
                "reasoning_chain": {"type": "string", "description": "1 sentence max"}
            },
            "required": [
                "target_metric", "target_page", "root_cause", "root_cause_evidence",
                "fix_category", "fix_description", "files_to_change", "files_to_NOT_touch",
                "estimated_improvement", "estimated_score_delta", "sonar_risk", "confidence_score", "reasoning_chain"
            ]
        }

        fix_plan = await call_with_structured_output(
            model, SYSTEM_PROMPT, USER_PROMPT, FIX_PLAN_SCHEMA
        )

        # STEP 8: Post-process and validate fix_plan
        available = set(state.get("relevant_files", [])) | set(file_map.get("file_contents", {}).keys())
        valid_files_to_change = []
        for f in fix_plan.get("files_to_change", []):
            if f.get("path") in available:
                valid_files_to_change.append(f)
        
        fix_plan["files_to_change"] = valid_files_to_change

        if not fix_plan["files_to_change"]:
            fix_plan["confidence_score"] = 0.1

        not_touch = set(fix_plan.get("files_to_NOT_touch", []))
        not_touch.update(state.get("forbidden_files", []))
        fix_plan["files_to_NOT_touch"] = list(not_touch)

        conf = fix_plan.get("confidence_score", 0.0)
        fix_plan["confidence_score"] = max(0.0, min(1.0, float(conf)))

        # Check fix memory
        recent_failures = state.get("fix_memory", {}).get("recent_failures", [])
        stack_name = file_map.get("stack", {}).get("framework", "")
        fix_cat = fix_plan.get("fix_category", "")
        
        if any(f.get("fix_type") == fix_cat and f.get("stack", "").lower() in stack_name.lower() for f in recent_failures):
            fix_plan["root_cause_evidence"] = str(fix_plan.get("root_cause_evidence", "")) + "\nWARNING: This approach has failed previously on this stack."
            fix_plan["confidence_score"] = max(0.0, fix_plan["confidence_score"] - 0.15)

        # STEP 9: Publish SSE with plan summary
        await sse.publish_metric_update(run_id, "reasoning_agent", {
            "target_page": fix_plan["target_page"],
            "target_metric": fix_plan["target_metric"],
            "fix_category": fix_plan["fix_category"],
            "files_to_change": [f["path"] for f in fix_plan.get("files_to_change", [])],
            "confidence_score": fix_plan["confidence_score"],
            "estimated_score_delta": fix_plan.get("estimated_score_delta", 0),
            "root_cause": fix_plan["root_cause"]
        })

        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_complete(run_id, "reasoning_agent", f"Generated fix plan for {fix_plan['target_metric']} (confidence: {fix_plan['confidence_score']:.2f})", duration_ms)

        # STEP 10: Return state update
        return {
            "fix_plan": fix_plan,
            "confidence_score": fix_plan["confidence_score"],
            "agent_steps": [{
                "agent": "reasoning_agent",
                "status": "complete",
                "summary": f"Generated fix plan: {fix_cat}",
                "duration_ms": duration_ms
            }],
            "current_agent": "reasoning_agent"
        }

    except Exception as exc:
        logger.exception("Reasoning agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "reasoning_agent", str(exc), duration_ms)
        
        return {
            "fix_plan": {},
            "confidence_score": 0.0,
            "error_log": [f"reasoning_agent error: {exc}"],
            "agent_steps": [{
                "agent": "reasoning_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "reasoning_agent"
        }
