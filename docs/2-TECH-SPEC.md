# Technical Specification

## System Architecture Overview

The system is designed as a 7-Layer LangGraph multi-agent architecture:

```text
Layer 7: Learning        [ Learning Agent ] <────────> [ Report Agent ]
                               │                              │
Layer 6: Deploy          [ Sandbox Agent ] ──────────> [ Deploy Agent ]
                               │                              │
Layer 5: Gates       [Syntax] -> [Quality] -> [Critic] -> [Dependency]
                               │
Layer 4: Fix Gen         [ Frontend Fix ] <────────> [ Backend Fix ]
                               │
Layer 3: Cognitive       [ Reasoning Agent ] ────────> [ Risk Classifier ]
                               │                              │
Layer 2: Intelligence [Metrics] [Codebase] [History] [Context]
                               │
Layer 1: Input           [ HTTP Trigger / Scheduler ]
```

## Tech Stack

| Component | Technology | Version | Why chosen |
| --- | --- | --- | --- |
| **Orchestration** | LangGraph | Latest | Provides cyclic graphs, interrupts, parallel nodes, and strict typing via `PipelineState` using `Annotated` reducers. |
| **Backend API** | FastAPI | Latest | High performance async capabilities ideal for `StreamingResponse` (SSE) and concurrent background tasks. |
| **Frontend** | Next.js | 15 | App router, React Server Components, clean UI structuring. |
| **Primary Database** | MongoDB Atlas | Latest | Motor async driver. Document nature maps perfectly to dynamic `run_summary` and `fix_memory` schemas. |
| **Message Broker** | Redis | Latest | Pub/Sub backend for reliable Server-Sent Events broadcasting to the frontend. |
| **Primary LLM** | Groq (llama-3.3-70b)| Latest | Insane inference speed (~800 tokens/sec), crucial for a fast pipeline. |
| **Fallback LLM** | Gemini 2.5 Flash | Latest | High rate limits, used if Groq hits 429s or context limits. |
| **Version Control** | GitHub API | REST | Native integration via `httpx` to read file trees, file contents, and create PRs. |
| **Sandbox** | Vercel API | Latest | Instant preview URLs for branch deployments without complex Docker-in-Docker CI/CD setups. |
| **Performance API** | PageSpeed Insights | REST | Official Core Web Vitals lab data metric source. |
| **Job Scheduler** | APScheduler | Latest | In-process cron-like scheduling for the automation layer. |
| **Validation** | Pydantic | V2 | Strict type enforcement for API payloads and LLM structured outputs. |
| **Logging** | Loguru | Latest | Colorful, thread-safe, structured logging. |
| **UI Styling** | Tailwind CSS | Latest | Rapid, utility-first UI styling. |
| **UI Components** | shadcn/ui | Latest | Radix primitives, highly customizable, accessible. |
| **Data Viz** | Recharts | Latest | For rendering historical performance metrics charts. |

## Agent Architecture

| # | Agent | Layer | Type | Input | Output | Failure Mode |
| - | --- | --- | --- | --- | --- | --- |
| 1 | `metrics_agent` | L2 | API | URL | `psi_metrics` | PSI Timeout -> 0 scores |
| 2 | `codebase_agent`| L2 | API | Repo | `file_map`, `relevant_files` | GitHub 404 -> Empty map |
| 3 | `history_agent` | L2 | DB | URL/Repo | `recent_runs`, `fix_memory`| Mongo down -> Empty lists |
| 4 | `context_agent` | L2 | Heuristic | File Map | `business_priority` | Safe fallback to LOW |
| 5 | `reasoning_agent`| L3 | LLM | L2 outputs | `fix_plan`, `confidence_score`| Token limit -> Truncation |
| 6 | `risk_classifier`| L3 | Heuristic | Plan | `risk_classification` | Fallback HIGH risk |
| 7 | `human_gate` | L3 | LangGraph | Plan/Risk | `human_approved` | Timeout -> Reject |
| 8 | `frontend_fix_agent`| L4 | LLM | Plan | `generated_fixes` (append) | Hallucination -> Syntax fail |
| 9 | `backend_fix_agent`| L4 | LLM | Plan | `generated_fixes` (append) | Hallucination -> Syntax fail |
| 10| `syntax_gate` | L5 | AST/Regex | Fixes | `syntax_gate` (PASS/FAIL) | Rejects valid but complex code |
| 11| `quality_gate` | L5 | Heuristic | Fixes | `quality_gate` (PASS/FAIL)| Fails on deep nesting/duplication |
| 12| `critic_agent` | L5 | LLM | Fixes | `critic_gate` (APPROVE/REJECT)| False positives in logic check |
| 13| `dependency_gate`| L5 | Graph Traversal | Fixes | `dependency_gate` | Misses dynamic imports |
| 14| `sandbox_agent` | L6 | API | Fixes/Branch | `sandbox_gate`, `sandbox_psi`| Vercel deploy timeout |
| 15| `deploy_agent` | L6 | API | Branch | PR URL, `deploy_status` | GitHub token scoped out |
| 16| `learning_agent` | L7 | DB | All State | DB Writes (Memories) | Silent DB fail |
| 17| `report_agent` | L7 | API/DB | All State | SSE Event, ROI | SSE connection drop |

## Data Flow

1. **Trigger:** User POSTs to `/run`. Backend initializes `PipelineState` with `run_id` and saves "running" status to Mongo. A background task starts `run_pipeline` via LangGraph.
2. **Layer 2 (Parallel):** Graph forks to `metrics_agent`, `codebase_agent`, `history_agent`, `context_agent`. Each mutates its distinct key in the state.
3. **Layer 3 (Sequential):** `merge_intelligence` syncs the parallel execution. `reasoning_agent` consumes L2 state to generate a `fix_plan`. `risk_classifier` determines routing. If HIGH risk, the graph hits the `interrupt()` at `human_gate_node` and pauses.
4. **Human Action:** Frontend calls POST `/approve`. Graph resumes.
5. **Layer 4 (Parallel):** `frontend_fix_agent` and `backend_fix_agent` consume the plan. They append to `generated_fixes` using `operator.add`.
6. **Layer 5 (Sequential):** `merge_fixes` syncs. Gates run sequentially: `syntax_gate` -> `quality_gate` -> `critic_agent` -> `dependency_gate`. If any fail, `retry_fix` increments `retry_count` and loops back to L4 (max 3 times).
7. **Layer 6:** `sandbox_agent` creates branch, deploys to Vercel, gets new PSI. Passes if PSI > Baseline. `deploy_agent` creates PR.
8. **Layer 7:** `learning_agent` saves to MongoDB. `report_agent` calculates ROI and broadcasts `run_complete` via Redis SSE.

## PipelineState Schema

Defined in `backend/state.py` as a `TypedDict`.

| Field | Type | Writer | Reader | Default |
| --- | --- | --- | --- | --- |
| `run_id` | str | `main.py` | All | - |
| `client_id` | str | `main.py` | Mongo Agents | `""` |
| `website_url` | str | `main.py` | Metrics, Sandbox | - |
| `repo_path` | str | `main.py` | Codebase, Deploy | - |
| `run_mode` | str | `main.py` | Deploy | `"SUPERVISED"` |
| `psi_metrics` | dict | `metrics_agent` | Reasoning, Report | `{}` |
| `backend_metrics`| list | `metrics_agent` | Reasoning | `[]` |
| `baseline_scores`| dict | `metrics_agent` | Sandbox | `{}` |
| `business_priority`| dict | `context_agent` | Reasoning, Risk | `{}` |
| `file_map` | dict | `codebase_agent` | Reasoning, Fixes | `{}` |
| `recent_runs` | list | `history_agent` | Reasoning | `[]` |
| `fix_memory` | dict | `history_agent` | Reasoning | `{}` |
| `fix_plan` | dict | `reasoning_agent`| Fixes, Risk | `{}` |
| `risk_classification`| str | `risk_classifier`| Router | `"LOW"` |
| `confidence_score`| float| `reasoning_agent`| Router | `0.0` |
| `generated_fixes`| list*| Fix Agents | Gates, Sandbox | `[]` |
| `retry_count` | int | `retry_fix` | Router | `0` |
| `sandbox_gate` | str | `sandbox_agent` | Router | `""` |
| `deploy_status` | str | `deploy_agent` | Report | `""` |
| `agent_steps` | list*| All Agents | SSE, Report | `[]` |
| `error_log` | list*| All Agents | Report | `[]` |
| `current_agent` | str | All Agents | SSE | `""` |

*(Uses `Annotated[list, operator.add]` for parallel mutation)*

## API Reference

| Method | Path | Request Body | Response | Description |
| --- | --- | --- | --- | --- |
| GET | `/health` | None | `HealthCheck` | Verifies Mongo, Redis, GitHub |
| POST | `/run` | `{"website_url": "...", "repo": "...", "run_mode": "..."}` | `{"run_id": "...", "status": "started"}` | Starts a pipeline |
| POST | `/stop/{id}` | None | `{"status": "success"}` | Aborts running pipeline |
| POST | `/approve/{id}`| `{"approved": true}` | `{"status": "resumed"}` | Resumes a human gate |
| GET | `/stream/{id}` | None | SSE Stream | Streams agent steps & status |
| GET | `/runs` | None | `List[Run]` | Gets last 10 runs |
| GET | `/run/{id}` | None | `Run` | Gets single run details |
| POST | `/schedule` | `{"cron": "0 0 * * *"}` | `{"status": "scheduled"}` | Configures cron job |

## SSE Event Schema

Server-Sent Events emitted by `SSEPublisher`:

- **`agent_start`**: Fired when `run(state)` begins.
  Payload: `{"agent_name": str, "timestamp": str, "input_summary": str}`
- **`agent_complete`**: Fired before `run(state)` returns.
  Payload: `{"agent_name": str, "timestamp": str, "duration_ms": int, "output_summary": str}`
- **`agent_error`**: Fired on exception.
  Payload: `{"agent_name": str, "error": str}`
- **`gate_result`**: Fired by gates.
  Payload: `{"gate_name": str, "result": "PASS|FAIL|APPROVE|REJECT|CLEAR|IMPACTED", "details": str}`
- **`metric_update`**: Fired by metrics/sandbox.
  Payload: `{"metric_type": "psi|backend", "data": dict}`
- **`human_approval_required`**: Fired at `human_gate_node`.
  Payload: `{"run_id": str, "risk_classification": str, "fix_plan": dict}`
- **`run_complete`**: Fired by `skip_run` or `report_agent`.
  Payload: `{"deploy_status": str, "roi": dict, "agent_steps": list, ...}`

## Database Schema

**MongoDB Collections:**

1. **`runs`**: Top level record.
   `_id`, `run_id` (string), `client_id` (string), `website_url` (string), `repo_path` (string), `run_mode` (string), `status` (string), `start_time` (datetime), `end_time` (datetime), `run_summary` (dict containing final pipeline state).
2. **`fix_memory`**: Learning database.
   `_id`, `client_id` (string), `fix_type` (string), `target_component` (string), `strategy_used` (string), `success` (bool), `psi_delta` (float), `timestamp` (datetime).
3. **`baselines`**: Historical performance tracking.
   `_id`, `client_id` (string), `url` (string), `latest_scores` (dict), `history` (list of dicts), `last_updated` (datetime).

## Security Model

- **Secret Management**: Handled entirely via backend `.env` (python-dotenv). Never committed. Frontend has no API keys.
- **GitHub Tokens**: Requires only `repo` scope to read codebase and open PRs. No admin scopes.
- **Data Isolation**: Multi-tenant isolation achieved by tagging all MongoDB documents with a `client_id`.
- **Never Committed**: `.env`, `.venv`, `.pytest_cache`, MongoDB connection strings.

## Performance Characteristics

- **PSI API**: ~15 seconds per page. Scanned in parallel (e.g. 5 pages = ~15-20s total).
- **Groq Inference**: Extreme low latency (~2-5s per massive reasoning call).
- **GitHub API**: Tree fetch (~2s), blob fetches (~1s per blob, max 10 blobs).
- **Sandbox Deployment**: 60 - 180 seconds (Vercel API build times).
- **Full Pipeline End-to-End**: 3 to 8 minutes.
- **SSE Connection**: Handled by Redis Pub/Sub, keepalive every 15s.
