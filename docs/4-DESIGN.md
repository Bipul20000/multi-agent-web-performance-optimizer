# Design System

## Design Philosophy
The UI for AWPIS is specifically designed to NOT look like a friendly SaaS tool. It is designed to feel like a **mission control dashboard** or a dark terminal interface. Managers using this tool should feel a sense of technical competence and real-time visibility as they watch the AI operate autonomously. We prioritize density of information, structural hierarchy, and distinct color-coding over white space and rounded, bubbly corners.

## Color System

**Backgrounds & Surfaces:**
- Background: `#0f1117` (Deep dark blue/gray for the main canvas)
- Surface: `#1a1d27` (Slightly lighter for cards and panels, creating depth)
- Border: `#2a2d3a` (Subtle delineation for card borders)

**Typography:**
- Text Primary: `#ffffff` (High contrast for readability)
- Text Secondary: `#94a3b8` (Muted slate for labels and metadata)

**Layer Accent Colors (Used strictly for AgentCard borders and icons):**
- Layer 2 Intelligence: `#0d9488` (Teal - represents gathering and sensing)
- Layer 3 Cognitive: `#3b82f6` (Blue - represents thinking and planning)
- Layer 4 Fix Gen: `#d97706` (Amber - represents construction and risk)
- Layer 5 Safety Gates: `#dc2626` (Red - represents security and blocking)
- Layer 6 Deploy: `#16a34a` (Green - represents success and shipping)
- Layer 7 Learning: `#9333ea` (Purple - represents memory and intelligence)

**Status Colors:**
- `waiting`: `#4b5563` (Gray border, dim text)
- `running`: Animated pulsing border inheriting the Layer Accent Color.
- `complete`: `#16a34a` (Solid green border, distinct checkmark)
- `failed`: `#dc2626` (Solid red border, X icon)
- `skipped`: `#d97706` (Solid amber border, warning icon)

## Typography
- **Font:** System font stack (`font-sans`). We deliberately avoid loading external fonts (like Google Fonts) as an ironic nod to performance optimization. The UI uses native OS rendering.
- **Headings:** `font-bold tracking-tight` (Crisp and dense).
- **Code/IDs:** `font-mono text-xs text-gray-400` (Used for run IDs, file paths, and logs).

## UI Patterns & Structure

Instead of heavily fragmented React components, the dashboard utilizes monolithic page layouts (`live/page.tsx` and `dashboard/page.tsx`) with distinct structural UI patterns:

- **Agent Cards (Inline):**
  - Rendered dynamically by mapping over the `LAYERS` array in `/live`.
  - **States:** waiting (dim), running (pulse), complete (green checkmark), failed (red error).
- **Log Terminal / Stream View:**
  - A central terminal window displaying raw SSE JSON logs chronologically.
- **Plan & Metrics Sidebar:**
  - A right-hand panel taking up 40% of the screen.
  - Displays: "Metrics Profile", "Confidence Score Gauge", and "Plan Details".
- **Executive Approval Widget (Inline):**
  - Appears at the top of the sidebar when `requiresApproval` is true.
  - **Actions:** "Approve & Deploy" button, "Reject" button.
- **KPI Grid:**
  - Dashboard top row showing Global Site Health, Score Improvement, Est Revenue Lift, and Optimizations Deployed. Uses HTML5 Canvas for sparklines.
- **Run Modal (Inline):**
  - Form dialog triggered from the Dashboard containing URL input and Mode toggle (Supervised/Automated).

## Page Layouts

1. `/dashboard`:
   - Full width layout.
   - Top row: 4 KPI patterns in a CSS grid (`grid-cols-4`).
   - Main body: Full-width table of recent runs.
2. `/live`:
   - 60/40 Split layout (`grid-cols-12`, col-span-8 and col-span-4).
   - Left side (60%): The pipeline visualization. Agents are stacked by layer.
   - Right side (40%): Plan & Metrics Sidebar. Executive Approval Widget overlays here.
3. `/history`:
   - Full width table layout.
   - Includes an area chart (Recharts) at the top showing historical PSI trends.
4. `/schedule`:
   - Centered, single-column form layout (`max-w-md mx-auto`) for entering cron expressions.

## Animation Patterns
- **Running Agent:** A CSS `@keyframes` pulse animation applied to the `ring` utility class. The card physically "glows" while active.
- **Agent Complete:** The pulse stops instantly. The border transitions to solid `#16a34a` over 150ms. The `duration_ms` text fades in from opacity 0.
- **Gate Pass:** The Lucide `Loader2` (spin) icon swaps to a `CheckCircle2` with a quick CSS scale bounce (`scale 0.9 -> 1.1 -> 1.0`).
- **Human Approval Widget:** Utilizes Framer Motion or CSS transitions to slide up from `translate-y-full` to `translate-y-0` when triggered.

## Responsive Behavior
This tool is strictly designed for **Desktop only** (`min-width: 1280px`). Engineering managers and DevOps personnel do not debug enterprise web performance architectures on their iPhones. Responsive breakpoints below `xl` are intentionally unoptimized.
