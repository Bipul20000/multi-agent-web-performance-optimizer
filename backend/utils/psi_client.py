"""PageSpeed Insights client — async fetching and parsing of Lighthouse metrics."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger as _logger

logger = _logger.bind(module=__name__)

# ── Custom exceptions ──────────────────────────────────────────────────────


class PSIError(Exception):
    """Raised when a PageSpeed Insights API call fails unrecoverably."""

    def __init__(
        self,
        message: str,
        url: str,
        status_code: int | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        super().__init__(message)

    def __repr__(self) -> str:
        return f"PSIError(url={self.url!r}, status_code={self.status_code})"


# ── Constants ──────────────────────────────────────────────────────────────

PSI_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Google Lighthouse rating thresholds
# Format: (good_upper_bound, needs_improvement_upper_bound)
_THRESHOLDS: dict[str, tuple[float, float]] = {
    "FCP": (1800.0, 3000.0),
    "LCP": (2500.0, 4000.0),
    "TBT": (200.0, 600.0),
    "CLS": (0.1, 0.25),
    "SI": (3400.0, 5800.0),
    "TTI": (3800.0, 7300.0),
    "INP": (200.0, 500.0),
    "TTFB": (800.0, 1800.0),
    "FID": (100.0, 300.0),
}

# Maps our short names → Lighthouse audit IDs
_METRIC_MAP: dict[str, str] = {
    "FCP": "first-contentful-paint",
    "LCP": "largest-contentful-paint",
    "TBT": "total-blocking-time",
    "CLS": "cumulative-layout-shift",
    "SI": "speed-index",
    "TTI": "interactive",
    "INP": "interaction-to-next-paint",
    "TTFB": "server-response-time",
    "FID": "max-potential-fid",
}

# Retryable HTTP status codes
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ── Internal helpers ───────────────────────────────────────────────────────


def _rate(metric: str, value: float) -> str:
    """Return 'good', 'needs-improvement', or 'poor' per Google thresholds."""
    thresholds = _THRESHOLDS.get(metric)
    if thresholds is None:
        return "unknown"
    good_bound, ni_bound = thresholds
    if value <= good_bound:
        return "good"
    if value <= ni_bound:
        return "needs-improvement"
    return "poor"


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_core_web_vitals(audits: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract Core Web Vitals from Lighthouse audits."""
    result: dict[str, dict[str, Any]] = {}
    for short_name, audit_id in _METRIC_MAP.items():
        audit = audits.get(audit_id, {})
        raw_value = _safe_float(audit.get("numericValue", 0.0))
        # CLS is unitless and needs more decimal precision
        if short_name == "CLS":
            value = round(raw_value, 3)
            unit = ""
        else:
            value = round(raw_value, 1)
            unit = "ms"
        result[short_name] = {
            "value": value,
            "unit": unit,
            "rating": _rate(short_name, raw_value),
        }
    return result


_FORCE_OPPORTUNITIES = frozenset({
    "render-blocking-resources", "unused-javascript", "unused-css-rules",
    "uses-optimized-images", "uses-text-compression", "uses-webp-images",
    "efficiently-encode-images", "uses-responsive-images"
})

def _parse_opportunities(audits: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract actionable opportunities sorted by savings descending."""
    opportunities: list[dict[str, Any]] = []
    for audit_id, audit in audits.items():
        details = audit.get("details", {})
        if details.get("type") == "opportunity":
            savings = _safe_float(details.get("overallSavingsMs", 0.0))
            if savings > 0 or audit_id in _FORCE_OPPORTUNITIES:
                opportunities.append(
                    {
                        "id": audit_id,
                        "title": audit.get("title", ""),
                        "savings_ms": round(savings, 1),
                        "description": audit.get("description", ""),
                    }
                )
    opportunities.sort(key=lambda o: o["savings_ms"], reverse=True)
    return opportunities


def _parse_diagnostics(audits: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract informative diagnostics from audits."""
    diagnostics: list[dict[str, Any]] = []
    for audit_id, audit in audits.items():
        if audit.get("scoreDisplayMode") == "informative":
            diagnostics.append(
                {
                    "id": audit_id,
                    "title": audit.get("title", ""),
                    "description": audit.get("description", ""),
                }
            )
    return diagnostics


def _parse_passed_audits(audits: dict[str, Any]) -> list[str]:
    """Return audit IDs that scored a perfect 1."""
    return sorted(
        audit_id
        for audit_id, audit in audits.items()
        if audit.get("score") == 1
    )


def _parse_category_scores(categories: dict[str, Any]) -> dict[str, float]:
    """Extract category scores as 0–100 floats."""
    mapping: list[tuple[str, str]] = [
        ("performance", "performance"),
        ("accessibility", "accessibility"),
        ("best-practices", "best_practices"),
        ("seo", "seo"),
    ]
    scores: dict[str, float] = {}
    for cat_key, our_key in mapping:
        cat = categories.get(cat_key, {})
        raw_score = cat.get("score")
        scores[our_key] = round(raw_score * 100, 1) if raw_score is not None else 0.0
    return scores


def _parse_response(
    data: dict[str, Any],
    url: str,
    strategy: str,
) -> dict[str, Any]:
    """Transform the raw PSI JSON response into our canonical shape."""
    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    perf_category = categories.get("performance", {})
    raw_perf_score = perf_category.get("score", 0.0)

    return {
        "url": url,
        "strategy": strategy,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scores": _parse_category_scores(categories),
        "core_web_vitals": _parse_core_web_vitals(audits),
        "opportunities": _parse_opportunities(audits),
        "diagnostics": _parse_diagnostics(audits),
        "passed_audits": _parse_passed_audits(audits),
        "raw_score": _safe_float(raw_perf_score),
    }


# ── Public API ─────────────────────────────────────────────────────────────


async def run_psi(
    url: str,
    api_key: str,
    strategy: str = "mobile",
    *,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Fetch PageSpeed Insights metrics for *url* with retry logic.

    Retries on HTTP 429 and 5xx up to *max_retries* with exponential backoff.

    Returns a structured dict with scores, core web vitals, opportunities,
    diagnostics, and passed audits.

    Raises:
        PSIError: On unrecoverable HTTP errors or after all retries exhausted.
    """
    params: dict[str, Any] = {
        "url": url,
        "key": api_key,
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }

    logger.info("Fetching PSI metrics for {} (strategy={})", url, strategy)

    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(PSI_API_URL, params=params)

            if response.status_code in _RETRYABLE_STATUS_CODES:
                wait = backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "PSI returned HTTP {} for {} — retry {}/{} in {:.1f}s",
                    response.status_code,
                    url,
                    attempt,
                    max_retries,
                    wait,
                )
                last_exception = PSIError(
                    f"PSI returned HTTP {response.status_code}",
                    url=url,
                    status_code=response.status_code,
                )
                if attempt < max_retries:
                    await asyncio.sleep(wait)
                continue

            if response.status_code != 200:
                error_body = response.text[:500]
                logger.error(
                    "PSI non-retryable error {} for {}: {}",
                    response.status_code,
                    url,
                    error_body,
                )
                raise PSIError(
                    f"PSI returned HTTP {response.status_code}: {error_body}",
                    url=url,
                    status_code=response.status_code,
                )

            try:
                data = response.json()
            except Exception as exc:
                raise PSIError(
                    f"Failed to parse PSI JSON response: {exc}",
                    url=url,
                    status_code=response.status_code,
                ) from exc

            parsed = _parse_response(data, url, strategy)

            logger.info(
                "PSI complete for {} ({}): perf={}, LCP={:.0f}ms ({}), "
                "{} opportunities, {} diagnostics",
                url,
                strategy,
                parsed["scores"]["performance"],
                parsed["core_web_vitals"]["LCP"]["value"],
                parsed["core_web_vitals"]["LCP"]["rating"],
                len(parsed["opportunities"]),
                len(parsed["diagnostics"]),
            )
            return parsed

        except PSIError:
            raise
        except httpx.TimeoutException as exc:
            wait = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "PSI timeout for {} — retry {}/{} in {:.1f}s",
                url,
                attempt,
                max_retries,
                wait,
            )
            last_exception = exc
            if attempt < max_retries:
                await asyncio.sleep(wait)
        except httpx.ConnectError as exc:
            wait = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "PSI connection error for {} — retry {}/{} in {:.1f}s: {}",
                url,
                attempt,
                max_retries,
                wait,
                exc,
            )
            last_exception = exc
            if attempt < max_retries:
                await asyncio.sleep(wait)
        except Exception as exc:
            logger.error("Unexpected error fetching PSI for {}: {}", url, exc)
            raise PSIError(
                f"Unexpected error: {exc}",
                url=url,
            ) from exc

    error_msg = f"PSI fetch failed after {max_retries} retries for {url}"
    logger.error(error_msg)
    raise PSIError(error_msg, url=url) from last_exception


async def run_psi_both_strategies(
    url: str,
    api_key: str,
) -> dict[str, dict[str, Any]]:
    """Run PSI for both mobile and desktop strategies in parallel.

    Returns ``{"mobile": {...}, "desktop": {...}}`` with the canonical
    metrics shape for each strategy.
    """
    logger.info("Running PSI for both strategies on {}", url)

    mobile_result, desktop_result = await asyncio.gather(
        run_psi(url, api_key, strategy="mobile"),
        run_psi(url, api_key, strategy="desktop"),
    )

    logger.info(
        "Both PSI strategies complete for {} — "
        "mobile_perf={}, desktop_perf={}",
        url,
        mobile_result["scores"]["performance"],
        desktop_result["scores"]["performance"],
    )
    return {"mobile": mobile_result, "desktop": desktop_result}
