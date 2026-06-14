# AWPIS Development Rules
# (System guardrails for development)

## The Prime Directives
1. **NEVER commit `.env` files.** Ever. No exceptions.
2. **NEVER deploy without sandbox validation first.** (Unless `DEMO_MODE=true` explicitly bypasses it).
3. **NEVER modify `forbidden_files`** (auth, payment flows, DB migrations). The codebase agent must filter these out before the reasoning agent sees them.
4. **NEVER let an agent raise an exception.** Every `run()` method must wrap its logic in `try/except` and return a dict (e.g. `{"error_log": ["..."]}`). Raising crashes LangGraph.
5. **NEVER skip the quality gates in production.**

## Adding a New Agent
If you (an AI or human) are adding a new agent, you must pass this checklist:

- [ ] Function signature is exactly: `async def run(state: PipelineState) -> dict`
- [ ] First executable line: `await publish_agent_start(...)` (SSE).
- [ ] Last executable line before return: `await publish_agent_complete(...)` (SSE).
- [ ] Entire body is wrapped in a `try/except Exception as e:`.
- [ ] Returns ONLY valid keys defined in `PipelineState`.
- [ ] If writing to a list field (`agent_steps`, `error_log`, `generated_fixes`):
      - Use: `state.get("field", []) + [new_item]`
      - **NOT**: `[new_item]` (This will overwrite the parallel reducer and crash the graph).
- [ ] Added as a node in `backend/graph.py` builder.
- [ ] Added to the architecture tables in `README.md` and `docs/2-TECH-SPEC.md`.

## State Rules
- `agent_steps`, `error_log`, and `generated_fixes` use `Annotated[list, operator.add]`. Do not change these to plain lists. Parallel agents will crash.
- Never overwrite state fields from another agent's domain (e.g., `metrics_agent` should not touch `file_map`).
- `confidence_score` must always be a float `0.0 - 1.0`. Clamp it if the LLM hallucinates `95`.
- `fix_plan` must always be a dictionary. Never `None`. Return an empty dict `{}` on failure.

## LLM Rules
- Always use the `call_with_structured_output` pattern for JSON responses.
- Always validate that required schema keys exist in Python after the LLM responds.
- Always strip markdown fences (` ```json ` and ` ``` `) from code generation responses before parsing.
- **Max prompt size for Groq:** ~10,000 characters. Groq has strict TPM limits on free/developer tiers.
- **Max `file_contents` preview:** Truncate to 150 characters per file in the `file_map` payload sent to `reasoning_agent`.

## Git Rules
- Branch naming convention: `awpis/fix-{run_id[:8]}` (e.g. `awpis/fix-19f0e8a1`).
- Never commit to `main` directly.
- PR required for all changes (even manual ones — eat your own dogfood).
- Commit message format: `type(scope): description` (Conventional Commits).
  - Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `chore`.

## Frontend Rules
- All API calls must use the `NEXT_PUBLIC_API_URL` environment variable. No hardcoded `localhost:8000`.
- **SSE Hook Rule:** Always use functional `setState` to avoid stale closures during rapid event streams.
  - ✅ `setAgentStates(prev => ({...prev, [name]: newState}))`
  - ❌ `setAgentStates({...agentStates, [name]: newState})`
- Never add browser storage (`localStorage` / `sessionStorage`) for pipeline data. Everything lives in the backend state.
- Layer colors are defined strictly in `docs/4-DESIGN.md`. Do not invent new Tailwind arbitrary color values for the UI.

## Security Rules
- `GITHUB_TOKEN` needs ONLY: `repo` (full), `workflow`.
- Do not request `admin`, `delete_repo`, or `org` scopes for the bot.
- MongoDB: Always filter queries by `client_id` to enforce multi-tenant isolation (even if there is only one tenant locally).
- SSE: Each `run_id` subscribes to its own Redis channel. Never broadcast a `run_id`'s events to a global channel.
- `GROQ_API_KEY`: Backend `main.py` and `gemini_client.py` only. Never exposed to Next.js.

## Extension Points
If you want to add capabilities:
- **New LLM provider:** Add it to `gemini_client.py` alongside the existing Groq/Gemini functions. Don't create a new client file.
- **New gate:** Add it between `dependency_gate` and `sandbox_agent` in `graph.py`.
- **New agent:** Follow the "Adding a New Agent" checklist above.
- **New metric:** Add parsing logic to `psi_client.py` in the Core Web Vitals extraction section.
- **New page:** Add to `frontend/app/` and update the sidebar navigation in `frontend/components/layout.tsx`.
