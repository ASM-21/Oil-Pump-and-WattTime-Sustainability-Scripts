# Documentation Roadmap

This roadmap captures the additional READMEs and supporting notes that would make the research archive easier to understand, show, and extend. The intent is to preserve the exploratory history while giving future readers a clear route through the strongest work.

## Documentation goals

1. **Orient quickly:** a reader should understand the major research threads within five minutes.
2. **Separate canonical from exploratory:** mature scripts should be easy to find, while older variants remain available as history.
3. **Support reproducibility:** each area should state inputs, outputs, environment assumptions, and external services.
4. **Show research value:** docs should connect scripts to thesis chapters, figures, tables, and future publications.
5. **Prepare for sharing:** sensitive credentials, local paths, and generated bulk data should be identified before public release.

## Recommended README set

| File | Purpose | Priority | Status |
| --- | --- | --- | --- |
| `README.md` | Repository-level landing page and project map. | High | Added |
| `WattTime Analysis Folder/README.md` | Explain the main carbon-aware scheduling workflow and Chapter 3 script families. | High | Added |
| `Machine Specific Scripts/README.md` | Clarify CNC/additive machine-energy scripts and how they relate to feature libraries. | High | Added |
| `OpenNX Feature Library Draft/README.md` | Explain the NXOpen CAD-phase energy estimator prototype. | High | Added |
| `openLCA Automation/README.md` | Explain OpenLCA GUI/static updater scripts and assumptions. | Medium | Added |
| `Background watttime scripts/README.md` | Mark early WattTime helper scripts as legacy/reference utilities. | Medium | Added |
| `docs/RESEARCH_STORY.md` | Narrative summary connecting manufacturing energy, grid signals, and LCA. | High | Added |
| `docs/REPRODUCIBILITY.md` | Environment, data availability, credentials, and rerun instructions. | High | Added |
| `docs/FIGURE_INDEX.md` | Map thesis/report figures to scripts, data inputs, and output files. | High | Added |
| `docs/DATA_INVENTORY.md` | List raw data, processed data, generated outputs, and what is omitted from Git. | High | Added |
| `docs/SECURITY_AND_SHARING_CHECKLIST.md` | Checklist for tokens, passwords, UUIDs, IP addresses, and local paths before public release. | High | Added |
| `docs/PROJECT_COMPLETION_CHECKLIST.md` | Practical handoff checklist for what is still missing before the repo feels complete. | High | Added |
| `docs/CANONICAL_WORKFLOWS.md` | Identify preferred workflows and deprecated/exploratory scripts. | High | Added |
| `docs/FUTURE_WORK.md` | Research extensions, cleanup tasks, and publication/portfolio next steps. | Medium | Added |

## Area-specific notes to add next

### WattTime analysis

- Identify the canonical script sequence for the final thesis/chapter workflow.
- Add a compact data-flow diagram: WattTime API/downloads → local library → processed run folder → Chapter 3 scripts → figures/tables.
- Create a table mapping each `ch3_*` script to the figure/table/research question it supports.
- Document the required folder structure for local WattTime data that is intentionally not committed.
- Add a short explanation of MOER, AOER, health-damage signals, and why each matters for manufacturing scheduling.

### Machine-specific scripts

- Add example input schemas for CNC and additive machine exports.
- Mark which scripts are one-off plotting experiments versus reusable feature-library analysis.
- Document how energy-per-feature values feed the OpenNX feature library or OpenLCA oil-pump model.
- Standardize output folder expectations so generated plots do not depend on an implicit working directory.

### OpenNX feature library

- Document the Siemens NX version/API assumptions.
- Provide a minimal run checklist for executing `main.py` inside NX.
- Explain the feature extraction output schema and how it connects to `aluminum_expanded.xlsx`.
- List unsupported or risky feature types so future researchers know where validation is needed.

### OpenLCA work

- Separate desktop-automation scripts from the `openlca-mcp` agent prototype.
- Document required OpenLCA database, IPC port, product-system UUIDs, LCIA method UUIDs, and expected reference results.
- Add screenshots or small example outputs for GUI tools once sensitive local IDs are removed.

### Background WattTime helpers

- Move credentials to environment variables before sharing.
- Preserve region discovery utilities as setup/reference scripts.
- Note which outputs are already superseded by the newer WattTime analysis pipeline.

## Suggested cleanup order

1. **Safety pass:** remove or rotate secrets and document environment-variable names.
2. **Landing docs:** finish the proposed `docs/RESEARCH_STORY.md` and `docs/REPRODUCIBILITY.md`.
3. **Canonical workflow pass:** rename or archive duplicate versioned scripts after deciding which ones are authoritative.
4. **Figure traceability:** build `docs/FIGURE_INDEX.md` so thesis/report visuals can be regenerated.
5. **Portfolio polish:** add diagrams, short example outputs, and a future-work section that highlights publishable extensions.

## README template for future subprojects

```markdown
# Subproject Name

## Purpose
One paragraph explaining the research question or tool role.

## Current status
Canonical / prototype / exploratory / legacy.

## Inputs
- Data files
- External tools/APIs
- Credentials or environment variables

## Outputs
- Figures
- Tables
- Reports
- Updated models/databases

## How to run
Step-by-step commands or application workflow.

## Key files
| File | Role |
| --- | --- |

## Notes and risks
Known limitations, local assumptions, missing validation, and next steps.
```

