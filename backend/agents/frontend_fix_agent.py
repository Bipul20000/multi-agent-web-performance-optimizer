"""Frontend fix agent — generates code changes for UI components and styles."""

from __future__ import annotations

import time
from typing import Any

from loguru import logger

from backend.config import get_settings
from backend.state import PipelineState
from backend.utils.gemini_client import call_for_code, get_groq_flash_model
from backend.utils.shared import get_github, get_publisher


def _is_frontend_file(path: str) -> bool:
    """Determine if a file path belongs to the frontend domain."""
    if "api/" in path:
        return False
    if path.endswith((".css", ".scss")):
        return True
    
    frontend_dirs = ("pages/", "app/", "components/", "src/pages/", "src/app/", "src/components/", "styles/", "src/styles/", "frontend/")
    frontend_exts = (".tsx", ".jsx", ".ts", ".js")
    
    if any(path.startswith(d) for d in frontend_dirs):
        if any(path.endswith(ext) for ext in frontend_exts):
            return True
            
    return False


async def run(state: PipelineState) -> dict[str, Any]:
    """Execute the frontend code generation phase."""
    run_id = state.get("run_id", "unknown")
    start_time = time.monotonic()
    sse = get_publisher()

    try:
        await sse.publish_agent_start(run_id, "frontend_fix_agent", "Generating frontend code changes")

        fix_plan = state.get("fix_plan", {})
        all_files_to_change = fix_plan.get("files_to_change", [])
        
        # Filter to frontend domain
        target_files = [f for f in all_files_to_change if _is_frontend_file(f.get("path", ""))]

        if not target_files:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            await sse.publish_agent_complete(run_id, "frontend_fix_agent", "No frontend files to change", duration_ms)
            return {
                "agent_steps": [{
                    "agent": "frontend_fix_agent",
                    "status": "complete",
                    "summary": "No frontend files to change",
                    "duration_ms": duration_ms
                }],
                "current_agent": "frontend_fix_agent"
            }

        file_map = state.get("file_map", {})
        file_contents = file_map.get("file_contents", {})
        gh = get_github()
        
        generated_fixes = []
        model = get_groq_flash_model(get_settings().GROQ_API_KEY)

        SYSTEM_PROMPT = """You are a performance engineer. Generate the minimally invasive 
code change to fix the described issue. Return ONLY the complete new file 
content, no explanations, no markdown fences."""

        for file_cmd in target_files:
            path = file_cmd.get("path")
            
            # 1. Get current file content
            content = file_contents.get(path)
            if content is None:
                try:
                    branch = await gh.get_default_branch()
                    file_res = await gh.get_file_content(path, branch)
                    content = file_res.get("content", "")
                except Exception as e:
                    logger.warning(f"Could not fetch {path} from GitHub: {e}")
                    continue
                    
            if not content:
                logger.warning(f"File {path} is empty or inaccessible")
                continue

            # 2. Call Gemini
            USER_PROMPT = f"""
Fix Category: {fix_plan.get('fix_category')}
Root Cause: {fix_plan.get('root_cause')}
File to Change: {path}
Instruction for this file: {file_cmd.get('specific_change')}

=== CURRENT FILE CONTENT ===
{content}
=== END CURRENT FILE CONTENT ===

Generate the complete updated file content:
"""
            
            try:
                logger.info(f"Generating frontend fix for {path}")
                new_content = await call_for_code(model, SYSTEM_PROMPT, USER_PROMPT)
                
                generated_fixes.append({
                    "path": path,
                    "original_content": content,
                    "new_content": new_content,
                    "agent": "frontend",
                    "fix_category": fix_plan.get("fix_category", "unknown"),
                    "change_summary": file_cmd.get("specific_change", "Applied fix")
                })
            except Exception as e:
                logger.error(f"Failed to generate code for {path}: {e}")

        # Merge with existing generated_fixes from other agents
        existing_fixes = state.get("generated_fixes", [])
        combined_fixes = existing_fixes + generated_fixes

        duration_ms = int((time.monotonic() - start_time) * 1000)
        summary = f"Generated {len(generated_fixes)} frontend file fixes"
        await sse.publish_agent_complete(run_id, "frontend_fix_agent", summary, duration_ms)

        return {
            "generated_fixes": combined_fixes,
            "agent_steps": [{
                "agent": "frontend_fix_agent",
                "status": "complete",
                "summary": summary,
                "duration_ms": duration_ms
            }],
            "current_agent": "frontend_fix_agent"
        }

    except Exception as exc:
        logger.exception("Frontend fix agent failed")
        duration_ms = int((time.monotonic() - start_time) * 1000)
        await sse.publish_agent_error(run_id, "frontend_fix_agent", str(exc), duration_ms)
        
        return {
            "error_log": [f"frontend_fix_agent error: {exc}"],
            "agent_steps": [{
                "agent": "frontend_fix_agent",
                "status": "error",
                "summary": f"Failed: {exc}",
                "duration_ms": duration_ms
            }],
            "current_agent": "frontend_fix_agent"
        }
