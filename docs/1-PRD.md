# AWPIS Product Requirements Document

## Problem Statement
Enterprise web properties continuously degrade in performance over time as new features, tracking scripts, and marketing tags are added. This creates a severe **enterprise web property degradation problem**. When core web vitals slip, the manual fix cycle typically takes 2-4 weeks—involving QA detection, Jira ticket creation, sprint planning, developer investigation, and deployment.

For large enterprises like Hero MotoCorp or major e-commerce platforms, a 1-second delay in page load time translates directly to millions in lost revenue, lower conversion rates, and reduced SEO visibility. Existing tools like Datadog or Lighthouse CI only *report* the degradation; they do not *fix* it.

| Feature | AWPIS | Datadog RUM | Lighthouse CI |
| :--- | :---: | :---: | :---: |
| Detects Degradation | ✅ | ✅ | ✅ |
| Analyzes Codebase | ✅ | ❌ | ❌ |
| Generates PRs | ✅ | ❌ | ❌ |
| Tests Fixes in Sandbox | ✅ | ❌ | ❌ |
| Self-healing / Rollbacks | ✅ | ❌ | ❌ |

## Product Vision
AWPIS transforms web performance from an observational metric into an autonomous, self-healing system. It acts as an elite, invisible performance engineering team that operates 24/7 to maintain optimal web vitals.

## Target Users
- **Primary:** Engineering managers at enterprises managing 10+ web properties who need to maintain performance SLAs without dedicating full-time engineers.
- **Secondary:** DevOps and Performance Engineers who configure the safety gates and review high-risk automated pull requests.
- **Tertiary:** Business Stakeholders (CMOs, Product VPs) who consume ROI reports linking speed improvements to estimated revenue lifts.

## Core User Stories
1. **As an Engineering Manager**, I want to trigger a manual run on a specific URL so that I can immediately generate a fix for a newly reported performance issue.
2. **As an Engineering Manager**, I want to configure scheduled runs (e.g., nightly) so that the system continuously optimizes the site without my intervention.
3. **As an Engineering Manager**, I want to view a live UI of the pipeline execution so that I can see exactly what each AI agent is analyzing and fixing in real time.
4. **As a DevOps Engineer**, I want to be prompted for human approval on high-risk fixes so that experimental changes don't break mission-critical flows like checkout.
5. **As a DevOps Engineer**, I want all generated fixes to pass through strict syntax and quality gates so that no secrets or broken code make it into a PR.
6. **As a DevOps Engineer**, I want every fix validated in a Vercel sandbox so that we mathematically guarantee a PageSpeed Insights improvement before deploying.
7. **As a Product Manager**, I want to review the history of all runs and their resulting PRs so that I can audit what the AI has done over the past month.
8. **As a Business Stakeholder**, I want the system to calculate an estimated ROI for each fix so that I can justify the investment in performance.
9. **As a Developer**, I want the system to remember past successful and failed fixes (Fix Memory) so that it doesn't propose the same bad change twice.
10. **As a Site Reliability Engineer**, I want the system to monitor production after a deploy and auto-revert within 90s if it detects a regression so that downtime is minimized.

## Functional Requirements

| Priority | Feature | Description |
| :---: | :--- | :--- |
| **P0** | PSI Scanning | Fetch Core Web Vitals via PageSpeed Insights API. |
| **P0** | LLM Reasoning | Synthesize metrics and codebase into a precise fix plan. |
| **P0** | Fix Generation | Generate syntax-correct React/Next.js code diffs. |
| **P0** | Quality Gates | Regex and AST-based validation for syntax and dependencies. |
| **P0** | Sandbox Testing | Deploy PR to Vercel preview and run PSI against it. |
| **P0** | GitHub PR | Open automated Pull Requests with the generated fix. |
| **P0** | Auto-Revert | Revert the commit if post-deploy PSI drops. |
| **P0** | SSE Streaming | Stream LangGraph agent states to the UI in real time. |
| **P0** | Live UI | Next.js dashboard showing agent states and human gates. |
| **P1** | Scheduler | APScheduler integration for daily/weekly runs. |
| **P1** | Fix Memory | MongoDB collection logging success/fail of past strategies. |
| **P1** | Baseline Tracking | Track historical performance of the URL to detect drifts. |
| **P1** | ROI Estimation | Map ms improvements to conversion rate bumps. |
| **P2** | Multi-tenant | Isolate data via `client_id` for SaaS capability. |
| **P2** | Slack/Email | Send notifications on completion or human approval. |
| **P2** | SonarQube | Integrate enterprise SAST into the Quality Gate. |

## Non-Functional Requirements
- **Performance:** The entire pipeline from detection to PR must complete in `< 15 minutes`.
- **Reliability:** Production regressions must trigger the auto-revert flow within 90 seconds of the bad deploy.
- **Security:** No secrets will be hardcoded. `GITHUB_TOKEN` is scoped minimally. The `syntax_gate` explicitly checks for AWS/GCP key patterns.
- **Scalability:** Multi-tenant ready database schema (MongoDB) grouping all runs and memories by `client_id`.

## Success Metrics
1. **Performance Lift:** Average PSI score improvement per run > 3 points.
2. **Safety:** Deployment success rate (sandbox passes) > 85%.
3. **Speed:** Mean Time to Resolution (MTTR) from detection to fix PR < 10 minutes.
4. **Business Impact:** Estimated conversion lift > 0.5% annualized across managed properties.

## Out of Scope (v1)
- Mobile app (iOS/Android) performance monitoring and patching.
- Non-GitHub repositories (Azure DevOps, GitLab, Bitbucket will be v2).
- Strict Service Level Agreement (SLA) guarantees for pipeline uptime.
