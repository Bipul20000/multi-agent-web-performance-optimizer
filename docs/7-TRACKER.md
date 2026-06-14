# Agent Memory / Build Tracker

This file is the memory of how AWPIS was built. 
If you are an AI agent extending this system in the future, **read this file first** before making any changes. It explains the "why" behind the code.

## Session Log

### Session 1 — Architecture Design
- **Goal:** Design an autonomous, self-healing performance system.
- **Decision:** Architected a 7-layer, 18-agent (logical) system using LangGraph.
- **Constraint Identified:** LangGraph's default state management overwrites keys if parallel nodes return the same key. We must use `Annotated[list, operator.add]` for anything parallel (like `generated_fixes`).
- **Tech Choices:** 
  - GitHub REST API over Azure DevOps (simpler demo).
  - Vercel Preview over Docker CI/CD (instant sandboxing).
  - Server-Sent Events (SSE) via Redis over WebSockets (one-directional state streaming is cleaner).

### Session 2 — Scaffold + Utils (Prompts 1-2)
- **Action:** Created `awpis/backend/utils/` clients.
- **Surprise:** GitHub API rate limits. Handled by scoping `github_client.py` to only fetch file trees, not every blob, unless explicitly requested by the Reasoning agent.

### Session 3 — Intelligence Agents (Prompt 3)
- **Action:** Built `metrics_agent`, `codebase_agent`, `history_agent`, `context_agent`.
- **Decision:** Mapped these as a parallel fan-out from the `START` node in `graph.py`.
- **Fix:** Had to write `merge_intelligence` to act as a synchronization barrier before Layer 3.

### Session 4 — Reasoning Core (Prompt 4)
- **Action:** Built `reasoning_agent` and `risk_classifier`.
- **Surprise:** Groq's `llama-3.3-70b` has a strict TPM (Tokens Per Minute) and Context Window limit that is much smaller than Gemini 1.5 Pro.
- **Fix:** Added aggressive string truncation in `reasoning_agent.py` to prevent 400 Payload Too Large errors when passing the `file_map`.

### Session 5 — Fix Generation (Prompt 5)
- **Action:** Built `frontend_fix_agent` and `backend_fix_agent`.
- **Decision:** Forced LLMs to return strict JSON arrays mapping `file_path` to `content`. Stripped markdown fences (```) in `gemini_client.py` because the LLM kept wrapping JSON in markdown despite instructions.

### Session 6 — Quality Gates (Prompt 6)
- **Action:** Implemented the 4 sequential gates.
- **Fix:** The `quality_gate` was too academic, failing standard React components. Bumped nesting limit from 5 to 10.
- **Decision:** Added a `retry_fix` loop. If a gate fails, it goes back to Fix Generation, incrementing `retry_count`. If `retry_count == 3`, graph routes to `skip_run`.

### Session 7 — Sandbox + Deploy (Prompt 7)
- **Action:** Built Vercel integration and GitHub PR logic.
- **Surprise:** Vercel API deployments are asynchronous. 
- **Fix:** Wrote a polling loop in `sandbox_agent.py` to wait for the Vercel deployment to hit "READY" before fetching the preview URL to run PSI against. Added a `SANDBOX_TIMEOUT` to `.env`.

### Session 8 — Learning + Reporting (Prompt 8)
- **Action:** Built MongoDB `fix_memory` writes and ROI calculation.
- **Decision:** ROI is estimated naively based on milliseconds of LCP improved. Purely illustrative for the dashboard.

### Session 9 — Frontend (Prompt 9)
- **Action:** Next.js 15 UI with dark "mission control" aesthetic.
- **Fix:** `useAgentStream` hook suffered from stale closures when updating the agent dictionary. Refactored to use `setAgentStates(prev => ({...prev, [name]: newState}))`.
- **Fix:** Added a 2-second delay to `main.py`'s `_run_with_delay` task to prevent the graph from outrunning the frontend SSE connection handshake.

## Architecture Decisions Log (ADR)

| # | Decision | Why | Alternatives rejected |
| - | --- | --- | --- |
| 1 | Groq over Gemini | Inference speed (800 tps) + Cost | OpenAI (expensive), local models (slow) |
| 2 | MemorySaver over PostgreSQL | Demonstration simplicity | PostgreSQL checkpointer (needs complex setup) |
| 3 | `operator.add` for lists | Required by LangGraph for parallel state merging | Custom dict reducers (overly complex) |
| 4 | 2s pipeline delay | Fixes SSE race condition where UI misses start events | Redis replay buffer (too complex for v1) |
| 5 | Vercel for Sandbox | Instant live URLs to run PageSpeed Insights against | Local Docker build + Ngrok (brittle, slow) |
| 6 | SSE over WebSockets | Server only ever pushes to client, client never pushes back | WebSockets (overkill, requires ping/pong logic) |

## File Map

- **`backend/graph.py`**: Compiles the LangGraph. Central nervous system. (Phase 2-7)
- **`backend/state.py`**: Defines `PipelineState` TypedDict. (Phase 2)
- **`backend/main.py`**: FastAPI routes, SSE streaming endpoint. (Phase 1, 8)
- **`backend/utils/gemini_client.py`**: LLM wrapper (Groq/Gemini). (Phase 1)
- **`backend/agents/metrics_agent.py`**: Hits PSI API. (Phase 3)
- **`backend/agents/codebase_agent.py`**: Fetches GitHub files. (Phase 3)
- **`backend/agents/history_agent.py`**: Reads MongoDB memories. (Phase 3)
- **`backend/agents/reasoning_agent.py`**: The main brain. (Phase 4)
- **`backend/agents/sandbox_agent.py`**: Vercel polling & validation. (Phase 7)
- **`backend/agents/deploy_agent.py`**: GitHub PR creator. (Phase 7)
- **`frontend/hooks/useAgentStream.ts`**: Connects Next.js to FastAPI SSE. (Phase 8)
- **`frontend/app/live/page.tsx`**: The main execution dashboard. (Phase 8)

## Dependency Graph (human readable)

- **`reasoning_agent`** reads: `psi_metrics` (from `metrics_agent`), `file_map` (from `codebase_agent`), `fix_memory` (from `history_agent`), `business_priority` (from `context_agent`).
- **`risk_classifier`** reads: `fix_plan` (from `reasoning_agent`), `business_priority`.
- **`frontend_fix_agent` / `backend_fix_agent`** reads: `fix_plan`, `file_map` content.
- **`syntax_gate` -> `dependency_gate`** read: `generated_fixes`.
- **`sandbox_agent`** reads: `generated_fixes`, `baseline_scores`.
- **`deploy_agent`** reads: `sandbox_gate`, `generated_fixes`.
- **`learning_agent`** reads: Everything (to construct a memory record).
