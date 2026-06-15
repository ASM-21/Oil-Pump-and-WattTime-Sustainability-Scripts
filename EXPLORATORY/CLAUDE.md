# CLAUDE.md — Exploratory research support for the JMSE journal extension

You are helping expand ASME MSEC 2026 paper MSEC2026-182984 into a journal article for the JMD/JMSE sustainability special issue, due **June 30, 2026**. This folder is your working area inside the owner's research repo. Everything you produce lives here; the rest of the repo is read-only reference.

## Read these first, in order
1. `context/PAPER_GOAL.md` — what the paper is and the conference-to-journal move.
2. `context/GROUND_TRUTH.md` — verified specs, numbers to verify, and the hard rules (no new data, no ecoinvent multiplier, additive only, no em dashes). **These rules are non-negotiable.**
3. `context/EXPANSION_DIRECTIONS.md` — the menu of candidate expansion directions to explore. This is the heart of the task.
4. `context/TRIAGE_code_vs_argument.md` — which claims need code and which are provable by argument from existing numbers.
5. `AGENT_BRIEF.md` — the build spec and ground rules for any direction that turns into a real analysis project.
6. `context/FOLLOWON_PATHWAYS.md` — larger directions that are horizon only, not for this paper.

## Your stance: explore first, build second
The goal is to **find which generalizations have substance**, not to mass-produce analyses. Most of what lifts this to a journal paper is argument from numbers already in hand, not new computation. So:

- **Default to cheap exploration.** For each direction, first see whether existing numbers already settle it (a `[desk]` or `[light analysis]` pass). Many will dead-end quickly, which is a fast, useful result. Write what you found in a short note before writing any heavy code.
- **Build only what a skeptical reviewer would not accept without the computation.** Per the triage, that is mainly the estimation-fidelity ladder and the allocation-rule analysis. Treat the other brief projects as candidates to explore lightly or defer, not as a checklist to complete.
- **One result per direction, then stop.** Get the first real finding, verify it, write it up, move on. Breadth across directions beats depth in one. Record next steps under "How to extend" rather than building them.
- **Do not write the paper.** Produce findings, figures, tables, and short notes the owner can lift. Do not draft full manuscript sections unless asked.

## Order of operations
1. **Discovery + loader gate** (AGENT_BRIEF section 0): wire the repo's existing loaders into `shared/adapters.py`, reconcile the operation count, confirm the gate passes. Nothing runs until existing data loads cleanly through the adapter. Reuse existing modules; do not rebuild pipelines.
2. **Cheap exploration pass:** work through the `[desk]` and `[light analysis]` directions in EXPANSION_DIRECTIONS (current best first bets: A1 utilization-factor landscape, B1 materials-dominate break-even, E3 uncertainty interval). Each gets a short note in `EXPLORATORY/explorations/<name>.md`: what you checked, what you found, whether it has legs.
3. **Targeted builds:** only for directions the cheap pass shows are fertile and that need computation, create a project folder per `AGENT_BRIEF.md` (copy `_example_project/`, use `shared/` style and checks, dual-path verify, smoke test, FINDINGS).
4. **Wrap up:** `EXPLORATORY/_summary.md` — which directions had substance (ranked), the computed numbers that resolve the scope doc's `[verify]` placeholders, every discrepancy found vs quoted numbers stated bluntly, and a one-line status per direction (promising / null / parked / built).

## Scaffolding already here
- `shared/style.py` — one ASME-friendly figure style (`apply_style`, `save_fig`).
- `shared/checks.py` — `CheckLog.cross_check` (dual-path), `check_against_expected` (vs quoted numbers), `require` (smoke tests).
- `shared/adapters.py` — the single data-access layer; fill its TODOs during discovery.
- `_example_project/run.py` — the canonical flow every build copies.
- `_templates/` — README and FINDINGS templates.

## What "good" looks like here
A handful of short, honest exploration notes that kill or confirm each direction fast, two well-verified analyses behind the paper's core new claims, figures and tables in ASME style ready to lift, and a blunt summary of what is real versus what was assumed. Null results are wins when they are fast and clear.
