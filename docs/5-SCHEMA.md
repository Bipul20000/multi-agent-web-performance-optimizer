# Data Schema

## MongoDB Collections

### Collection: `runs`
Stores the complete lifecycle of every pipeline execution.
- **Indexes:** `run_id` (unique), `client_id` (hashed), `start_time` (descending).

| Field | Type | Description | Example |
| --- | --- | --- | --- |
| `_id` | ObjectId | MongoDB internal ID | `64b5f8...` |
| `run_id` | string | Unique execution UUID | `a1b2c3d4e5` |
| `client_id` | string | Multi-tenant isolation ID | `org_99x` |
| `website_url` | string | Target URL analyzed | `https://demo.vercel.app` |
| `repo_path` | string | Target GitHub repo | `user/repo` |
| `run_mode` | string | SUPERVISED or AUTOMATED | `SUPERVISED` |
| `status` | string | Current run status | `running`, `completed`, `failed`, `aborted` |
| `start_time` | datetime | Pipeline start timestamp | `2024-06-14T10:00:00Z` |
| `end_time` | datetime | Pipeline completion timestamp | `2024-06-14T10:05:00Z` |
| `run_summary`| object | Final snapshot of `PipelineState`| `{ deploy_status: "success", ... }` |

### Collection: `fix_memory`
The persistent learning store. Used by `history_agent` to prevent repeating mistakes.
- **Indexes:** `fix_type` + `target_component` (compound), `timestamp` (descending).

| Field | Type | Description | Example |
| --- | --- | --- | --- |
| `_id` | ObjectId | MongoDB internal ID | - |
| `client_id` | string | Multi-tenant isolation ID | `org_99x` |
| `fix_type` | string | Category of fix applied | `next_image_optimization` |
| `target_component`| string | File or module changed | `app/components/Hero.tsx` |
| `strategy_used`| string | Brief description of the logic | `Added priority=true to LCP image` |
| `success` | bool | Did sandbox PSI improve? | `true` |
| `psi_delta` | float | Point change in score | `+4.5` |
| `timestamp` | datetime | When this memory was created | `2024-06-14T10:05:00Z` |

### Collection: `baselines`
Tracks historical PSI scores to detect regressions and determine Sandbox pass/fail.
- **Indexes:** `url` (unique).

| Field | Type | Description | Example |
| --- | --- | --- | --- |
| `_id` | ObjectId | MongoDB internal ID | - |
| `client_id` | string | Multi-tenant isolation ID | `org_99x` |
| `url` | string | The URL being tracked | `https://demo.vercel.app` |
| `latest_scores`| object | The most recent PSI data | `{ mobile: 78, desktop: 92 }` |
| `history` | list | Array of previous `latest_scores`| `[{ date: ..., scores: ... }]` |
| `last_updated`| datetime | Last time this was modified | `2024-06-14T10:05:00Z` |

## PipelineState (LangGraph)
Defined as a `TypedDict` in `backend/state.py`.

- **`run_id`** (str): UUID.
- **`client_id`** (str): Tenant ID.
- **`website_url`** (str): URL being optimized.
- **`repo_path`** (str): GitHub `owner/repo`.
- **`run_mode`** (str): SUPERVISED or AUTOMATED.
- **`psi_metrics`** (dict): PageSpeed data from `metrics_agent`.
- **`backend_metrics`** (list): APM data (if any).
- **`baseline_scores`** (dict): From MongoDB via `metrics_agent`.
- **`business_priority`** (dict): Map of file path to "HIGH/MED/LOW" from `context_agent`.
- **`file_map`** (dict): Repo tree from `codebase_agent`.
- **`relevant_files`** (list): Target files for fix generation.
- **`forbidden_files`** (list): Files agents are barred from touching.
- **`recent_runs`** (list): Last 10 runs from `history_agent`.
- **`fix_memory`** (dict): Memories relevant to current files.
- **`fix_plan`** (dict): Output of `reasoning_agent` (issue, strategy, diff spec).
- **`risk_classification`** (str): Output of `risk_classifier` ("HIGH/LOW").
- **`confidence_score`** (float): 0.0-1.0 from `reasoning_agent`.
- **`human_approved`** (bool): Result of `human_gate_node` interrupt.
- **`generated_fixes`** (`Annotated[list, operator.add]`): Parallel append from Fix agents. Shape: `{"file": str, "content": str}`.
- **`critic_feedback`** (str): Reason for reject from `critic_agent`.
- **`retry_count`** (int): Tracks gate loop iterations.
- **`syntax_gate`**, **`quality_gate`**, **`critic_gate`**, **`dependency_gate`** (str): Gate outputs ("PASS/FAIL").
- **`sandbox_url`** (str): Vercel preview URL.
- **`sandbox_psi`** (dict): PSI results for the preview URL.
- **`sandbox_gate`** (str): "APPROVE/REJECT".
- **`pr_url`** (str): GitHub PR link.
- **`deploy_status`** (str): Final outcome string.
- **`production_psi_after`** (dict): Auto-revert monitor data.
- **`auto_reverted`** (bool): Auto-revert triggered flag.
- **`langsmith_trace_id`** (str): Observability ID.
- **`error_log`** (`Annotated[list, operator.add]`): Collected exceptions.
- **`total_duration_ms`** (int): Pipeline timing.
- **`current_agent`** (str): Which agent is running (for SSE).
- **`agent_steps`** (`Annotated[list, operator.add]`): Audit log of everything that happened.

## SSE Event Payloads

Events emitted via Redis Pub/Sub in `backend/utils/sse_publisher.py`.

**`agent_start`**
```json
{
  "type": "agent_start",
  "data": {
    "agent_name": "metrics_agent",
    "timestamp": "2024-06-14T10:00:00.123Z",
    "input_summary": "Fetching PSI for / and /checkout"
  }
}
```

**`agent_complete`**
```json
{
  "type": "agent_complete",
  "data": {
    "agent_name": "metrics_agent",
    "timestamp": "2024-06-14T10:00:15.000Z",
    "duration_ms": 14877,
    "output_summary": "Retrieved LCP: 3.2s, CLS: 0.1"
  }
}
```

**`gate_result`**
```json
{
  "type": "gate_result",
  "data": {
    "gate_name": "syntax_gate",
    "result": "PASS",
    "details": "AST parsing successful, no secrets found."
  }
}
```

**`human_approval_required`**
```json
{
  "type": "human_approval_required",
  "data": {
    "run_id": "a1b2c3d4e5",
    "risk_classification": "HIGH",
    "fix_plan": {"issue": "...", "strategy": "..."}
  }
}
```

**`run_complete`**
```json
{
  "type": "run_complete",
  "data": {
    "deploy_status": "success",
    "roi": { "estimated_revenue_lift_usd": 12500, "conversion_lift_pct": 0.4 },
    "agent_steps": [ ... ]
  }
}
```

## GitHub Branch Naming
All AWPIS generated branches follow the format: `awpis/fix-{run_id[:8]}`
Example: `awpis/fix-a1b2c3d4`

## PR Body Template
Generated by `deploy_agent.py`:

```markdown
# 🤖 AWPIS Automated Performance Fix

## Issue Identified
{state['fix_plan'].get('issue')}

## Strategy Implemented
{state['fix_plan'].get('strategy')}

## Validation
- **Syntax Gate**: ✅ Passed
- **Quality Gate**: ✅ Passed
- **Critic Agent**: ✅ Approved
- **Sandbox Result**: ✅ Improved (LCP dropped by {delta}ms)

---
*Generated autonomously by the AWPIS agentic pipeline.*
*Run ID: {run_id}*
```
