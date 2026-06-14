"""Codebase agent — analyzes repo structure, tech stack, and code contents."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from loguru import logger

from backend.state import PipelineState
from backend.utils.shared import get_github, get_publisher

PERFORMANCE_RED_FLAGS = {
    "unoptimized_images": r'<img\s[^>]*src=',
    "console_logs": r'console\.(log|warn|error)',
    "sync_scripts": r'<script\s(?!.*async|.*defer)',
    "inline_styles": r'style=\{',
}

def _detect_stack(package_json: str) -> dict[str, str | bool]:
    """Parse package.json and detect framework, stylings, bundler, etc."""
    try:
        pkg = json.loads(package_json)
        deps = pkg.get("dependencies", {})
        dev_deps = pkg.get("devDependencies", {})
        all_deps = {**deps, **dev_deps}
        
        framework = "unknown"
        if "next" in all_deps: framework = "nextjs"
        elif "nuxt" in all_deps: framework = "nuxt"
        elif "astro" in all_deps: framework = "astro"
        elif "vue" in all_deps: framework = "vue"
        elif "react" in all_deps: framework = "react"
            
        styling = "unknown"
        if "tailwindcss" in all_deps: styling = "tailwind"
        elif "styled-components" in all_deps: styling = "styled-components"
        elif "sass" in all_deps: styling = "sass"
            
        bundler = "unknown"
        if "webpack" in all_deps: bundler = "webpack"
        elif "vite" in all_deps: bundler = "vite"
        elif "turbopack" in all_deps: bundler = "turbopack"
            
        return {
            "framework": framework,
            "styling": styling,
            "bundler": bundler,
            "typescript": "typescript" in all_deps
        }
    except Exception:
        return {
            "framework": "unknown",
            "styling": "unknown",
            "bundler": "unknown",
            "typescript": False
        }


def _match_glob(path: str, patterns: list[str]) -> bool:
    """Super basic glob matcher for the specific patterns we use."""
    for pattern in patterns:
        if pattern.endswith("**"):
            prefix = pattern[:-2]
            if path.startswith(prefix): return True
        elif pattern.endswith("*"):
            prefix = pattern[:-1]
            if path.startswith(prefix): return True
        elif pattern.startswith("**/*"):
            suffix = pattern[4:]
            if path.endswith(suffix): return True
        elif path == pattern:
            return True
    return False


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute codebase analysis phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    
    sse = get_publisher()
    gh = get_github()

    try:
        await sse.publish_agent_start(run_id, "codebase_agent", "Analyzing repository codebase")

        # STEP 2 — Get repo file tree
        branch = await gh.get_default_branch()
        file_tree = await gh.get_file_tree(branch)

        # STEP 3 — Detect framework and stack
        package_json_content = "{}"
        try:
            # Try frontend/package.json first for monorepos, then root
            try:
                pkg_file = await gh.get_file_content("frontend/package.json", branch)
            except Exception:
                pkg_file = await gh.get_file_content("package.json", branch)
            package_json_content = pkg_file.get("content", "{}")
        except Exception:
            logger.warning("No package.json found")
            
        stack_info = _detect_stack(package_json_content)
        
        # Check for TS files if not found in package.json
        if not stack_info["typescript"]:
            has_ts = any(f["path"].endswith(".ts") or f["path"].endswith(".tsx") for f in file_tree)
            stack_info["typescript"] = has_ts

        # STEP 4 — Categorize files
        categorized: dict[str, list[str]] = {
            "frontend_critical": [],
            "styles": [],
            "config": [],
            "api_routes": [],
            "assets": []
        }
        
        frontend_patterns = [
            "pages/**", "app/**", "components/**", 
            "src/pages/**", "src/app/**", "src/components/**",
            "frontend/src/pages/**", "frontend/src/app/**", "frontend/src/components/**",
            "frontend/pages/**", "frontend/app/**", "frontend/components/**"
        ]
        style_patterns = ["**/*.css", "**/*.scss", "tailwind.config.*", "globals.css", "frontend/src/index.css"]
        config_patterns = ["next.config.*", "vercel.json", "package.json", "tsconfig.json", "frontend/package.json", "frontend/vite.config.js"]
        api_patterns = ["pages/api/**", "app/api/**", "src/pages/api/**", "backend/routes/**", "backend/controllers/**"]
        asset_patterns = ["public/**", "frontend/public/**", "src/assets/**", "frontend/src/assets/**"]
        
        frontend_exts = (".tsx", ".jsx", ".ts", ".js")
        
        for item in file_tree:
            path = item["path"]
            
            # Exclude tests
            if ".test." in path or ".spec." in path or ".stories." in path:
                continue
                
            if _match_glob(path, config_patterns):
                categorized["config"].append(path)
            elif _match_glob(path, api_patterns):
                categorized["api_routes"].append(path)
            elif _match_glob(path, style_patterns):
                categorized["styles"].append(path)
            elif _match_glob(path, asset_patterns):
                categorized["assets"].append(path)
            elif _match_glob(path, frontend_patterns) and path.endswith(frontend_exts):
                categorized["frontend_critical"].append(path)

        # STEP 5 — Fetch content of top performance-relevant files
        paths_to_fetch = list(categorized["config"])
        
        # Try to match worst page
        worst_page = ""
        psi_metrics = state.get("psi_metrics", {})
        if psi_metrics:
            worst_page_tuple = min(psi_metrics.items(), key=lambda x: x[1]["mobile"]["scores"]["performance"])
            worst_page = worst_page_tuple[0]
            
        if worst_page and worst_page != "/":
            page_name = worst_page.strip("/")
            for p in categorized["frontend_critical"]:
                if page_name in p:
                    paths_to_fetch.append(p)
                    
        # Add largest frontend files
        frontend_files = [f for f in file_tree if f["path"] in categorized["frontend_critical"]]
        frontend_files.sort(key=lambda x: x["size"], reverse=True)
        paths_to_fetch.extend(f["path"] for f in frontend_files[:10])
        
        paths_to_fetch.extend(categorized["api_routes"])
        
        # Deduplicate and cap
        paths_to_fetch = list(dict.fromkeys(paths_to_fetch))[:20]
        
        logger.info(f"Fetching {len(paths_to_fetch)} files")
        
        file_contents = {}
        # Batch fetch
        for i in range(0, len(paths_to_fetch), 5):
            batch = paths_to_fetch[i:i+5]
            results = await asyncio.gather(
                *[gh.get_file_content(p, branch) for p in batch],
                return_exceptions=True
            )
            for path, res in zip(batch, results):
                if isinstance(res, BaseException):
                    logger.warning(f"Failed to fetch {path}: {res}")
                elif res.get("too_large"):
                    logger.info(f"Skipping too large file {path}")
                else:
                    file_contents[path] = res.get("content", "")

        # STEP 6 — Extract performance patterns
        performance_patterns: dict[str, dict[str, list[str]]] = {
            "red_flags": {k: [] for k in PERFORMANCE_RED_FLAGS},
            "good_patterns": {"next_image": [], "dynamic_import": [], "memo": []}
        }
        
        for path, content in file_contents.items():
            if not (path.endswith(".js") or path.endswith(".jsx") or path.endswith(".ts") or path.endswith(".tsx")):
                continue
                
            for flag, pattern in PERFORMANCE_RED_FLAGS.items():
                if re.search(pattern, content):
                    performance_patterns["red_flags"][flag].append(path)
                    
            if "next/image" in content: performance_patterns["good_patterns"]["next_image"].append(path)
            if "dynamic(" in content or "lazy(" in content: performance_patterns["good_patterns"]["dynamic_import"].append(path)
            if "React.memo" in content or "useMemo" in content or "useCallback" in content:
                performance_patterns["good_patterns"]["memo"].append(path)

        # Large deps check
        try:
            pkg = json.loads(package_json_content)
            deps = str(pkg.get("dependencies", {}))
            if "moment" in deps or "lodash" in deps:
                performance_patterns["red_flags"]["large_dependencies"] = ["package.json"]
        except Exception:
            pass

        # STEP 7 — Get recent commits
        from backend.config import get_settings
        if get_settings().DEMO_MODE.lower() == "true":
            recent_commits = []
        else:
            recent_commits = await gh.get_recent_commits(branch, limit=5)

        # STEP 8 — Build maps
        file_map = {
            "framework": stack_info["framework"],
            "stack": stack_info,
            "total_files": len(file_tree),
            "categorized": categorized,
            "file_contents": file_contents,
            "performance_patterns": performance_patterns,
            "recent_commits": recent_commits
        }
        
        # Determine relevant files
        relevant_files = []
        # First files with red flags
        for paths in performance_patterns["red_flags"].values():
            relevant_files.extend(paths)
        # Then matched page file
        if worst_page and worst_page != "/":
            page_name = worst_page.strip("/")
            for p in categorized["frontend_critical"]:
                if page_name in p: relevant_files.append(p)
        # Pad with other frontend files
        relevant_files.extend(categorized["frontend_critical"])
        
        relevant_files = list(dict.fromkeys(relevant_files))[:15]
        
        forbidden_files = []
        for item in file_tree:
            p = item["path"]
            if ".test." in p or ".spec." in p or p.endswith(".lock") or ".env" in p or "migration" in p.lower() or "auth" in p.lower() or "[...nextauth]" in p:
                forbidden_files.append(p)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary = f"Mapped {len(file_tree)} files. Framework: {stack_info['framework']}. Found {len(file_contents)} relevant contents."
        
        await sse.publish_agent_complete(run_id, "codebase_agent", summary, duration_ms)

        # STEP 9 — Return state
        return {
            "file_map": file_map,
            "relevant_files": relevant_files,
            "forbidden_files": forbidden_files,
            "agent_steps": [{
                "agent": "codebase_agent",
                "status": "complete",
                "summary": summary,
                "duration_ms": duration_ms
            }],
            "current_agent": "codebase_agent"
        }

    except Exception as exc:
        logger.exception("Codebase agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "codebase_agent", str(exc), duration_ms)
        
        return {
            "file_map": {},
            "relevant_files": [],
            "forbidden_files": [],
            "error_log": [f"codebase_agent error: {exc}"],
            "agent_steps": [{
                "agent": "codebase_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "codebase_agent"
        }
