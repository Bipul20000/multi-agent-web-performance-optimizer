#!/usr/bin/env python3
"""Seed demo data into MongoDB for the AWPIS dashboard."""

import asyncio
from datetime import datetime, timezone, timedelta
import uuid

from motor.motor_asyncio import AsyncIOMotorClient

async def seed_data():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.awpis
    
    # Check if already seeded
    if await db.runs.count_documents({}) > 0:
        print("Demo data already seeded.")
        return

    now = datetime.now(timezone.utc)
    demo_url = "https://demo.vercel.app"

    # --- 1. Seed Runs ---
    runs_data = [
        # 1. Success
        {
            "run_id": str(uuid.uuid4()),
            "website_url": demo_url,
            "client_id": "demo",
            "start_time": (now - timedelta(days=1, hours=2)).isoformat(),
            "end_time": (now - timedelta(days=1, hours=1, minutes=58)).isoformat(),
            "status": "complete",
            "deploy_status": "deployed",
            "run_summary": {
                "target_page": "/",
                "target_metric": "LCP",
                "fix_category": "image_optimization",
                "roi": {
                    "score_before": 42.0,
                    "score_after": 67.0,
                    "scores_before": {"performance": 42.0, "accessibility": 90.0, "best_practices": 85.0, "seo": 80.0},
                    "scores_after": {"performance": 67.0, "accessibility": 90.0, "best_practices": 85.0, "seo": 80.0},
                    "score_delta": 25.0,
                    "estimated_conversion_lift_pct": 1.25,
                    "message": "Performance score delta: 25.0. Estimated conversion lift: ~1.25%"
                },
                "agent_steps": [
                    {"agent": "metrics_agent", "duration_ms": 1200, "summary": "Metrics collected"},
                    {"agent": "reasoning_agent", "duration_ms": 3400, "summary": "Fix plan generated"},
                    {"agent": "frontend_fix_agent", "duration_ms": 2500, "summary": "Optimized Next/Image usage"},
                    {"agent": "quality_gate", "duration_ms": 150, "summary": "Passed"},
                    {"agent": "deploy_agent", "duration_ms": 8000, "summary": "PR deployed. Status: deployed"}
                ]
            },
            "final_score": 67.0,
            "pr_url": "https://github.com/demo/repo/pull/101"
        },
        # 2. Success
        {
            "run_id": str(uuid.uuid4()),
            "website_url": demo_url,
            "client_id": "demo",
            "start_time": (now - timedelta(days=2)).isoformat(),
            "end_time": (now - timedelta(days=2, minutes=-2)).isoformat(),
            "status": "complete",
            "deploy_status": "deployed",
            "run_summary": {
                "target_page": "/products",
                "target_metric": "FCP",
                "fix_category": "font_loading",
                "roi": {
                    "score_before": 55.0,
                    "score_after": 71.0,
                    "scores_before": {"performance": 55.0, "accessibility": 88.0, "best_practices": 80.0, "seo": 95.0},
                    "scores_after": {"performance": 71.0, "accessibility": 88.0, "best_practices": 80.0, "seo": 95.0},
                    "score_delta": 16.0,
                    "estimated_conversion_lift_pct": 0.8,
                },
                "agent_steps": [
                    {"agent": "metrics_agent", "duration_ms": 1100, "summary": "Metrics collected"},
                    {"agent": "reasoning_agent", "duration_ms": 2900, "summary": "Fix plan generated"},
                    {"agent": "frontend_fix_agent", "duration_ms": 2100, "summary": "Added font-display: swap"},
                    {"agent": "deploy_agent", "duration_ms": 6500, "summary": "PR deployed. Status: deployed"}
                ]
            },
            "final_score": 71.0,
            "pr_url": "https://github.com/demo/repo/pull/100"
        },
        # 3. Success
        {
            "run_id": str(uuid.uuid4()),
            "website_url": demo_url,
            "client_id": "demo",
            "start_time": (now - timedelta(days=3)).isoformat(),
            "end_time": (now - timedelta(days=3, minutes=-3)).isoformat(),
            "status": "complete",
            "deploy_status": "deployed_supervised",
            "run_summary": {
                "target_page": "/blog",
                "target_metric": "TBT",
                "fix_category": "caching_headers",
                "roi": {
                    "score_before": 38.0,
                    "score_after": 59.0,
                    "scores_before": {"performance": 38.0, "accessibility": 95.0, "best_practices": 75.0, "seo": 85.0},
                    "scores_after": {"performance": 59.0, "accessibility": 95.0, "best_practices": 75.0, "seo": 85.0},
                    "score_delta": 21.0,
                    "estimated_conversion_lift_pct": 1.05,
                },
                "agent_steps": [
                    {"agent": "metrics_agent", "duration_ms": 1400, "summary": "Metrics collected"},
                    {"agent": "backend_fix_agent", "duration_ms": 3100, "summary": "Added cache-control headers"},
                    {"agent": "deploy_agent", "duration_ms": 12000, "summary": "PR deployed. Status: deployed_supervised"}
                ]
            },
            "final_score": 59.0,
            "pr_url": "https://github.com/demo/repo/pull/98"
        },
        # 4. Reverted
        {
            "run_id": str(uuid.uuid4()),
            "website_url": demo_url,
            "client_id": "demo",
            "start_time": (now - timedelta(hours=5)).isoformat(),
            "end_time": (now - timedelta(hours=4, minutes=55)).isoformat(),
            "status": "complete",
            "deploy_status": "reverted",
            "auto_reverted": True,
            "run_summary": {
                "target_page": "/about",
                "target_metric": "CLS",
                "fix_category": "layout_shifts",
                "roi": {
                    "score_before": 61.0,
                    "score_after": 58.0,
                    "scores_before": {"performance": 61.0, "accessibility": 90.0, "best_practices": 90.0, "seo": 90.0},
                    "scores_after": {"performance": 58.0, "accessibility": 90.0, "best_practices": 90.0, "seo": 90.0},
                    "score_delta": -3.0,
                    "estimated_conversion_lift_pct": 0,
                    "message": "Regression detected: 61.0 -> 58.0"
                },
                "agent_steps": [
                    {"agent": "metrics_agent", "duration_ms": 1050, "summary": "Metrics collected"},
                    {"agent": "frontend_fix_agent", "duration_ms": 4000, "summary": "Fixed dynamic height issues"},
                    {"agent": "deploy_agent", "duration_ms": 15000, "summary": "PR deployed. Status: reverted (regression)"}
                ]
            },
            "final_score": 58.0,
            "pr_url": "https://github.com/demo/repo/pull/105"
        },
        # 5. Skipped
        {
            "run_id": str(uuid.uuid4()),
            "website_url": demo_url,
            "client_id": "demo",
            "start_time": (now - timedelta(minutes=45)).isoformat(),
            "end_time": (now - timedelta(minutes=43)).isoformat(),
            "status": "complete",
            "deploy_status": "skipped",
            "risk_classification": "SKIP",
            "run_summary": {
                "target_page": "/checkout",
                "target_metric": "LCP",
                "fix_category": "payment_gateway_sync",
                "confidence_score": 0.22,
                "roi": {
                    "score_before": 45.0,
                    "score_after": 45.0,
                    "scores_before": {"performance": 45.0, "accessibility": 100.0, "best_practices": 95.0, "seo": 100.0},
                    "scores_after": {"performance": 45.0, "accessibility": 100.0, "best_practices": 95.0, "seo": 100.0},
                    "score_delta": 0.0,
                    "estimated_conversion_lift_pct": 0,
                },
                "agent_steps": [
                    {"agent": "metrics_agent", "duration_ms": 1000, "summary": "Metrics collected"},
                    {"agent": "reasoning_agent", "duration_ms": 3000, "summary": "Low confidence score: 0.22. Skipping."}
                ]
            },
            "final_score": 45.0
        }
    ]
    await db.runs.insert_many(runs_data)

    # --- 2. Seed Fix Memory ---
    memory_data = [
        {"timestamp": now.isoformat(), "fix_type": "image_optimization", "stack": "nextjs", "metric_targeted": "LCP", "before": 42.0, "after": 67.0, "success": True, "side_effects": [], "page_type": "landing"},
        {"timestamp": now.isoformat(), "fix_type": "font_loading", "stack": "nextjs", "metric_targeted": "FCP", "before": 55.0, "after": 71.0, "success": True, "side_effects": [], "page_type": "content"},
        {"timestamp": now.isoformat(), "fix_type": "caching_headers", "stack": "nextjs", "metric_targeted": "TBT", "before": 38.0, "after": 59.0, "success": True, "side_effects": [], "page_type": "content"},
        {"timestamp": now.isoformat(), "fix_type": "component_splitting", "stack": "nextjs", "metric_targeted": "LCP", "before": 65.0, "after": 55.0, "success": False, "side_effects": ["CLS increased"], "page_type": "dynamic"},
        {"timestamp": now.isoformat(), "fix_type": "third_party_removal", "stack": "nextjs", "metric_targeted": "TBT", "before": 30.0, "after": 25.0, "success": False, "side_effects": ["broke analytics"], "page_type": "landing"},
        {"timestamp": now.isoformat(), "fix_type": "lazy_loading", "stack": "nextjs", "metric_targeted": "LCP", "before": 40.0, "after": 55.0, "success": True, "side_effects": [], "page_type": "blog"},
        {"timestamp": now.isoformat(), "fix_type": "lazy_loading", "stack": "nextjs", "metric_targeted": "LCP", "before": 45.0, "after": 60.0, "success": True, "side_effects": [], "page_type": "product"},
        {"timestamp": now.isoformat(), "fix_type": "lazy_loading", "stack": "nextjs", "metric_targeted": "LCP", "before": 50.0, "after": 52.0, "success": False, "side_effects": [], "page_type": "cart"}
    ]
    await db.fix_memory.insert_many(memory_data)

    # --- 3. Seed Baselines ---
    await db.baselines.insert_one({
        "url": demo_url,
        "scores": {
            "performance": 58,
            "accessibility": 91,
            "best_practices": 83,
            "seo": 79
        },
        "updated_at": now.isoformat()
    })

if __name__ == "__main__":
    asyncio.run(seed_data())
