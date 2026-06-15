# AWPIS: Autonomous Web Performance Intelligence System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/release/python-3100/)
[![Next.js 15](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**AWPIS** is an elite, autonomous AI engineering team that lives in your codebase. It continuously monitors your web properties for performance degradations, automatically generates precise code fixes, tests them in a secure sandbox, and opens pull requests—all without human intervention.

Think of it as having a dedicated performance engineer working 24/7 to keep your site lightning-fast, optimizing your Core Web Vitals to drive higher SEO rankings and user conversions.

---

## Project Documentation

For a deep dive into how AWPIS was built and how to extend it, check out our comprehensive documentation folder:

- **[Product Requirements (PRD)](./docs/1-PRD.md)** - Vision, users, and success metrics.
- **[Technical Specification](./docs/2-TECH-SPEC.md)** - Deep dive into the LangGraph architecture.
- **[Application Flow](./docs/3-APP-FLOW.md)** - Step-by-step user journeys.
- **[Design System](./docs/4-DESIGN.md)** - The "Mission Control" UI aesthetic guide.
- **[Data Schema](./docs/5-SCHEMA.md)** - MongoDB and PipelineState structures.
- **[Implementation Plan](./docs/6-IMPLEMENTATION-PLAN.md)** - How the project was built phase-by-phase.
- **[Agent Memory & Tracker](./docs/7-TRACKER.md)** - Architecture Decisions Log (ADR).
- **[Development Rules](./docs/8-RULES.md)** - **MUST READ:** Guardrails and rules for extending the codebase.

---

## Table of Contents
- [Why AWPIS?](#-why-awpis)
- [How It Works](#-how-it-works)
- [System Architecture](#-system-architecture)
- [Quick Start](#-quick-start)
- [Environment Variables](#-environment-variables)
- [Tech Stack](#-tech-stack)
- [Contributing](#-contributing)
- [License](#-license)

---

## Why AWPIS?

Enterprise web applications inevitably slow down as new features, heavy images, and tracking scripts are added. Typically, fixing these issues takes weeks of manual work: detection, ticketing, investigation, coding, and deployment.

AWPIS changes this paradigm:
- **Instant Detection:** It regularly fetches your Core Web Vitals via Google PageSpeed Insights.
- **AI-Driven Code Fixes:** It analyzes your GitHub repository and uses powerful LLMs (like Groq's LLaMA 3.3) to write exact React/Next.js code patches to fix the root cause.
- **Mathematically Proven:** It deploys the fix to a Vercel preview URL and runs PageSpeed Insights *again*. If the score doesn't improve, the fix is discarded.
- **Safety First:** Strict security and syntax gates ensure no broken code or secrets are ever committed.

---

## How It Works?

AWPIS uses a multi-agent orchestration pipeline powered by LangGraph. When a run is triggered:

1. **Intelligence Gathering:** Four AI agents wake up in parallel. They fetch live performance metrics, read your source code from GitHub, review past fixes from MongoDB, and assess the business priority of the impacted pages.
2. **Cognitive Reasoning:** A central Reasoning Agent synthesizes this massive context and formulates a step-by-step fix plan.
3. **Safety & Human Oversight:** A Risk Classifier scores the plan. If it's a high-risk change, the pipeline pauses and pings a human manager via a sleek Next.js UI to review and approve the strategy.
4. **Code Generation:** Parallel coding agents generate the actual diffs for frontend and backend files.
5. **Quality Gauntlet:** The code is aggressively scanned for syntax errors, cognitive complexity, and circular dependencies. An adversarial AI "Critic" reviews the code one last time.
6. **Sandbox Validation:** The code is pushed to a temporary branch and deployed to Vercel. Only if the performance mathematically improves does it proceed.
7. **Deployment:** A polished Pull Request is opened on GitHub. AWPIS commits the successful strategy to its memory database to learn over time.

---

## System Architecture

<img width="2186" height="1419" alt="diagram-export-14-6-2026-4_13_38-PM" src="https://github.com/user-attachments/assets/8dfc509f-a907-44c0-832f-bec664cfef94" />

AWPIS is built on a 7-layer autonomous framework:

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

---

## Quick Start

Follow these steps to get AWPIS running locally.

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- Docker Desktop (for running MongoDB and Redis)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url> awpis && cd awpis
   ```

2. **Set up the Environment:**
   Copy the example file and fill in your API keys (see [Environment Variables](#-environment-variables) below).
   ```bash
   cp .env.example .env
   ```

3. **Start the Database Infrastructure:**
   Spin up MongoDB and Redis in the background.
   ```bash
   docker-compose up -d
   ```

4. **Install Backend Dependencies:**
   Create a virtual environment and install the Python requirements.
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **Install Frontend Dependencies:**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

6. **Start the Application:**
   Run the boot script which will start both the FastAPI backend and the Next.js frontend concurrently.
   ```bash
   ./start.sh
   ```

7. **Open the Dashboard:**
   Visit [http://localhost:3000/dashboard](http://localhost:3000/dashboard) to trigger your first autonomous run!

---

## Environment Variables

To operate, AWPIS requires access to several external APIs. Configure these in your `.env` file.

| Key | Description | Required | Example |
| --- | --- | :---: | --- |
| `GROQ_API_KEY` | Powers the primary ultra-fast AI reasoning engine. | ✅ | `gsk_abc...` |
| `GEMINI_API_KEY` | Fallback AI engine in case of rate limits. | ✅ | `AIza...` |
| `GITHUB_TOKEN` | Personal Access Token to read code and create PRs. | ✅ | `ghp_123...` |
| `GITHUB_REPO` | The target repository you want to optimize. | ✅ | `username/my-site` |
| `WEBSITE_URL` | The live URL of the target repository. | ✅ | `https://my-site.com` |
| `PSI_API_KEY` | Google PageSpeed Insights API key. | ✅ | `AIza...` |
| `MONGODB_URI` | Connection string for MongoDB. | ✅ | `mongodb://localhost:27017` |
| `REDIS_URL` | Connection string for Redis (handles live UI streaming). | ✅ | `redis://localhost:6379` |
| `VERCEL_TOKEN` | Token to trigger sandbox deployments. | ✅ | `ab12...` |
| `RUN_MODE` | Pipeline mode: `SUPERVISED` (asks for approval) or `AUTOMATED`. | ✅ | `SUPERVISED` |
| `DEMO_MODE` | Set to `true` to skip strict security gates during presentations. | ❌ | `true` |

---


## Tech Stack

AWPIS utilizes a modern, high-performance stack:

- **Orchestration:** [LangGraph](https://python.langchain.com/docs/langgraph) (Complex multi-agent cyclical graphs)
- **AI Models:** [Groq LLaMA 3.3](https://groq.com/) (Speed) & [Google Gemini 2.5](https://deepmind.google/technologies/gemini/) (Fallback)
- **Backend API:** [FastAPI](https://fastapi.tiangolo.com/) (Async Python, Server-Sent Events)
- **Frontend UI:** [Next.js 15](https://nextjs.org/) (React, App Router, Tailwind CSS, shadcn/ui)
- **Databases:** [MongoDB](https://www.mongodb.com/) (State & Memory) & [Redis](https://redis.io/) (Pub/Sub)
- **Infrastructure:** GitHub REST API, Vercel REST API, PageSpeed Insights API

---

## Contributing

We welcome contributions! To ensure AWPIS remains stable and secure:
1. Please read **[docs/8-RULES.md](./docs/8-RULES.md)** before writing any code.
2. Create a feature branch: `git checkout -b feature/my-new-agent`
3. If adding an agent, ensure it properly streams its status to the UI and handles errors gracefully without crashing the graph.
4. Submit a Pull Request.

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.
