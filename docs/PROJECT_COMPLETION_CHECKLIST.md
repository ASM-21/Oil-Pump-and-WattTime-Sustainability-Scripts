# Project Completion Checklist

This checklist answers the practical question: **what is still missing for this GitHub repo to be easy to pick up, reproduce, and extend?** It is intentionally written as a working punch list rather than a polished narrative.

## Highest-impact missing pieces

| Priority | Missing piece | Why it matters | Suggested artifact |
| --- | --- | --- | --- |
| P0 | Secret cleanup and sharing policy | The repo contains research scripts that may include credentials, tokens, IP addresses, UUIDs, and local paths. These must be removed or documented before public sharing. | `docs/SECURITY_AND_SHARING_CHECKLIST.md`, `.env.example`, updated `.gitignore` |
| P0 | Reproducible environment | A new student or future-you needs to know the Python version, package versions, external apps, and OS assumptions. | `requirements.txt` or per-folder requirements, `environment.yml`, `docs/REPRODUCIBILITY.md` |
| P0 | Data inventory | The code depends on local WattTime data, machine logs, OpenLCA databases, Excel libraries, and generated outputs that may not be committed. | `docs/DATA_INVENTORY.md` |
| P0 | Canonical workflow definition | Multiple scripts are versioned or exploratory, so a reader cannot yet tell which scripts are final versus historical. | `docs/CANONICAL_WORKFLOWS.md` and/or archive folders |
| P1 | Figure/table traceability | Thesis, paper, or portfolio figures should map back to exact scripts, inputs, and output files. | `docs/FIGURE_INDEX.md` |
| P1 | Research story / project narrative | The repo needs a concise explanation of the research question, contribution, and how WattTime, machine energy, NX, and OpenLCA fit together. | `docs/RESEARCH_STORY.md` |
| P1 | Example data and smoke tests | Future users need something small they can run without private data or licensed software. | `examples/`, `tests/`, sample CSV/JSON outputs |
| P1 | Dependency boundaries by area | Some folders require Siemens NX, OpenLCA, WattTime API access, or Ollama; others can run with plain Python. | Per-folder README prerequisites |
| P2 | Issue backlog / future work | Good future work ideas are spread across memory and script comments instead of one visible backlog. | GitHub issues or `docs/FUTURE_WORK.md` |
| P2 | Consistent naming and folder conventions | Spaces, version suffixes, and typo-heavy filenames make automation and onboarding harder. | Rename plan in `docs/REFACTOR_PLAN.md` |

## What a new person needs on day one

A new researcher should be able to answer these questions without asking you directly:

1. **What is the main research contribution?**
   - Add a one-page research story that explains the sustainability workflow from machine energy to grid-aware scheduling to LCA.
2. **Which folder should I start with?**
   - Keep the root README as the map, but add a stronger `Start here if...` section for thesis review, code reproduction, LCA work, and CAD-feature work.
3. **What can I run today?**
   - Identify scripts that run with committed/sample data versus scripts that require private data or external desktop software.
4. **What data is missing from Git?**
   - List private/local data sources, expected folder paths, file formats, units, date ranges, and access restrictions.
5. **Which outputs are trustworthy?**
   - Mark canonical generated summaries and final figures separately from exploratory plots.
6. **How do I avoid breaking the research record?**
   - Add conventions for archiving old scripts, adding new scripts, and documenting changes.

## Recommended files to add next

### 1. `docs/RESEARCH_STORY.md`

Suggested sections:

- Research problem and motivation.
- Main contribution in plain language.
- System boundary: machine energy, grid emissions, CAD features, OpenLCA oil-pump model.
- Thesis/report chapter mapping.
- What is complete versus future work.
- A simple diagram or bullet flow:
  `Machine/CAD energy → WattTime grid signal → scheduling heuristic → emissions/LCA interpretation`.

### 2. `docs/REPRODUCIBILITY.md`

Suggested sections:

- Supported OS and Python versions.
- Folder-specific setup instructions.
- Python dependencies and virtual-environment commands.
- External tools: WattTime account, Siemens NX, OpenLCA desktop/IPC, Ollama if using `openlca-mcp`.
- How to rerun the most important WattTime/Chapter 3 outputs.
- Known non-reproducible pieces due to private data or licensed software.

### 3. `docs/DATA_INVENTORY.md`

Suggested table columns:

| Dataset/artifact | Used by | Format | Committed? | Source/access | Notes |
| --- | --- | --- | --- | --- | --- |
| WattTime raw data library | WattTime analysis | Parquet/CSV | No/partial | WattTime API | Include date range, regions, signal types. |
| Machine energy traces | Machine-specific scripts | CSV/Excel | TBD | Lab machine export | Include units and sampling rate. |
| OpenLCA database | OpenLCA automation/MCP | OpenLCA DB | No | Local OpenLCA | Include database/version and product system names. |
| NX feature library | OpenNX draft | XLSX | Yes | Derived from machining energy measurements | Document units and assumptions. |

### 4. `docs/FIGURE_INDEX.md`

Suggested table columns:

| Figure/table | Script | Inputs | Output path | Final? | Notes |
| --- | --- | --- | --- | --- | --- |

This is one of the best portfolio/research-polish improvements because it proves that figures are traceable and repeatable.

### 5. `docs/SECURITY_AND_SHARING_CHECKLIST.md`

Suggested checklist:

- Remove committed token files.
- Replace hardcoded usernames/passwords with environment variables.
- Replace private IP addresses and local absolute paths with configuration values.
- Decide whether UUIDs identify private OpenLCA databases and should be redacted.
- Confirm WattTime data redistribution terms.
- Add `.env.example` and `.gitignore` patterns for local secrets and caches.
- Rotate any credential that was ever committed.

### 6. `docs/CANONICAL_WORKFLOWS.md`

Suggested sections:

- WattTime Chapter 3 workflow.
- Machine-energy-to-feature-library workflow.
- NX feature-estimation workflow.
- OpenLCA oil-pump update workflow.
- Agent/MCP OpenLCA query workflow.
- Deprecated or historical scripts.

## Suggested repo structure after cleanup

This is a target structure, not something that needs to happen in one commit:

```text
.
├── README.md
├── docs/
│   ├── DOCUMENTATION_ROADMAP.md
│   ├── PROJECT_COMPLETION_CHECKLIST.md
│   ├── RESEARCH_STORY.md
│   ├── REPRODUCIBILITY.md
│   ├── DATA_INVENTORY.md
│   ├── FIGURE_INDEX.md
│   ├── SECURITY_AND_SHARING_CHECKLIST.md
│   └── CANONICAL_WORKFLOWS.md
├── examples/
│   ├── watttime_sample/
│   ├── machine_energy_sample/
│   └── openlca_sample_outputs/
├── tests/
│   └── lightweight smoke tests that do not require private data
├── WattTime Analysis Folder/
├── Machine Specific Scripts/
├── OpenNX Feature Library Draft/
├── openLCA Automation/
├── openlca-mcp/
└── Background watttime scripts/
```

## Definition of "complete enough"

The repo is complete enough for handoff when a future user can do the following:

- Read the root README and understand the project in under five minutes.
- Identify the canonical workflow for each research thread.
- Install dependencies or understand why a workflow requires licensed software.
- Run at least one smoke test or sample workflow without private data.
- Trace each final thesis/report figure back to a script and input dataset.
- Know what data is missing from Git and how to request or recreate it.
- Avoid exposing secrets when cloning, publishing, or extending the repo.
- See a clear future-work backlog that distinguishes cleanup from research extensions.

## Suggested next three improvement passes

1. **Security follow-through**
   - Rotate exposed credentials, decide whether to rewrite Git history before public release, and keep `.env` local only.
2. **Sample-data pass**
   - Add tiny anonymized WattTime-like, CNC/additive, OpenNX, and OpenLCA example artifacts under `examples/`.
3. **Canonical-output pass**
   - Fill in exact run folders, output filenames, and final/candidate status in `docs/FIGURE_INDEX.md` and `docs/DATA_INVENTORY.md`.
