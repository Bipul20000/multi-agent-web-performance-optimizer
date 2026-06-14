"""Metrics agent — runs PageSpeed Insights and checks backend health."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger

from backend.state import PipelineState
from backend.utils.psi_client import run_psi_both_strategies
from backend.utils.shared import get_mongo, get_publisher

_COMMON_PAGES = ["/about", "/contact", "/products", "/services", "/blog"]
_API_ROUTES = ["/api/health", "/api/status"]


async def _check_page_exists(url: str, timeout: float = 5.0) -> bool:
    """Do a HEAD request to check if a page exists (200/301/302)."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.head(url, follow_redirects=True)
            return response.status_code in (200, 301, 302)
    except Exception as exc:
        logger.debug(f"Page check failed for {url}: {exc}")
        return False


async def _check_api_endpoint(url: str, timeout: float = 5.0) -> dict[str, Any] | None:
    """Do a GET request to an API endpoint to check health and response time."""
    start_time = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, follow_redirects=True)
            duration_ms = (time.monotonic() - start_time) * 1000
            return {
                "endpoint": urlparse(url).path,
                "status_code": response.status_code,
                "response_time_ms": round(duration_ms, 2),
            }
    except Exception as exc:
        logger.debug(f"API check failed for {url}: {exc}")
        return None


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the metrics collection phase."""
    run_id = state.get("run_id", "unknown")
    website_url = state.get("website_url", "").rstrip("/")
    start_time = time.monotonic()

    sse = get_publisher()
    mongo = get_mongo()

    try:
        await sse.publish_agent_start(
            run_id,
            "metrics_agent",
            f"Running PSI on {website_url}",
        )

        if not website_url:
            raise ValueError("website_url is missing from state")

        # STEP 2 — Determine pages to scan
        candidate_paths = {"/"}  # Homepage always included
        
        # Add priority pages if configured
        priority_config = state.get("business_priority", {})
        if priority_config:
            candidate_paths.update(priority_config.keys())
            
        # Add common paths
        candidate_paths.update(_COMMON_PAGES)

        # Build full URLs and check if they exist
        urls_to_check = [urljoin(website_url, path) for path in candidate_paths]
        
        exist_results = await asyncio.gather(
            *[_check_page_exists(url) for url in urls_to_check],
            return_exceptions=True
        )

        valid_urls = []
        for url, exists in zip(urls_to_check, exist_results):
            if isinstance(exists, bool) and exists:
                valid_urls.append(url)

        # Cap at 5 pages
        urls_to_scan = valid_urls[:5]
        logger.info(f"Scanning {len(urls_to_scan)} pages: {urls_to_scan}")

        # STEP 3 — Run PSI on all pages
        from backend.config import get_settings
        api_key = get_settings().PSI_API_KEY
        
        psi_results = await asyncio.gather(
            *[run_psi_both_strategies(url, api_key) for url in urls_to_scan],
            return_exceptions=True
        )

        psi_metrics: dict[str, Any] = {}
        for url, result in zip(urls_to_scan, psi_results):
            path = urlparse(url).path or "/"
            if isinstance(result, Exception):
                logger.warning(f"PSI failed for {url}: {result}")
                continue
            psi_metrics[path] = result

        if not psi_metrics:
            raise ValueError("PSI failed for all pages")

        # STEP 4 — Find worst performing page
        worst_page = ""
        worst_score = 101.0
        worst_metric = ""

        for path, data in psi_metrics.items():
            mobile_score = data["mobile"]["scores"]["performance"]
            if mobile_score < worst_score:
                worst_score = mobile_score
                worst_page = path
                
                # Find worst CWV
                cwv = data["mobile"].get("core_web_vitals", {})
                for metric, details in cwv.items():
                    rating = details.get("rating", "good")
                    if rating == "poor":
                        worst_metric = metric
                        break
                    elif rating == "needs-improvement" and worst_metric != "poor":
                        worst_metric = metric

        # STEP 5 — Check backend health
        api_urls = [urljoin(website_url, route) for route in _API_ROUTES]
        api_results = await asyncio.gather(
            *[_check_api_endpoint(url) for url in api_urls],
            return_exceptions=True
        )
        
        backend_metrics: list[dict[str, Any]] = []
        for res in api_results:
            if isinstance(res, dict):
                backend_metrics.append(res)
                
        # Also check homepage explicitly for response time
        hp_check = await _check_api_endpoint(website_url)
        if isinstance(hp_check, dict):
            backend_metrics.append(hp_check)

        # STEP 6 — Load baseline
        baseline = await mongo.get_baseline(website_url)
        baseline_delta = None
        if baseline and "scores" in baseline:
            baseline_score = baseline["scores"].get("performance", 0.0)
            baseline_delta = worst_score - baseline_score

        # STEP 7 — Publish metric update
        await sse.publish_metric_update(
            run_id,
            "metrics_agent",
            {
                "pages_scanned": len(psi_metrics),
                "worst_page": worst_page,
                "worst_score": worst_score,
                "worst_scores": psi_metrics[worst_page]["mobile"]["scores"] if worst_page else {},
                "worst_metric": worst_metric,
                "baseline_delta": baseline_delta,
            }
        )

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary_text = f"Scanned {len(psi_metrics)} pages. Worst: {worst_page} at {worst_score}/100"
        
        await sse.publish_agent_complete(run_id, "metrics_agent", summary_text, duration_ms)

        # STEP 8 — Return state
        return {
            "psi_metrics": psi_metrics,
            "backend_metrics": backend_metrics,
            "baseline_scores": baseline or {},
            "agent_steps": [{
                "agent": "metrics_agent",
                "status": "complete",
                "summary": summary_text,
                "duration_ms": duration_ms
            }],
            "current_agent": "metrics_agent"
        }

    except Exception as exc:
        logger.exception("Metrics agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "metrics_agent", str(exc), duration_ms)
        
        return {
            "psi_metrics": {},
            "error_log": [f"metrics_agent error: {exc}"],
            "agent_steps": [{
                "agent": "metrics_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "metrics_agent"
        }
