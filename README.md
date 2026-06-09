# Oil Pump and WattTime Sustainability Scripts

This repository is a working research archive for MS-level sustainability work connecting manufacturing energy data, WattTime grid-emissions signals, Siemens NX feature extraction, and OpenLCA oil-pump life-cycle analysis. It currently contains several project threads at different maturity levels, so the goal of these docs is to make the archive easier to navigate, safer to share, and clearer for future thesis/publication work.

## Quick orientation

| Area | Maturity | What it is | Start here |
| --- | --- | --- | --- |
| `WattTime Analysis Folder/` | Most developed research workflow | Numbered analysis pipeline and Chapter 3 scripts for carbon-aware manufacturing scheduling using WattTime MOER/AOER/health signals. | [`WattTime Analysis Folder/README.md`](WattTime%20Analysis%20Folder/README.md) |
| `openlca-mcp/` | Prototype with tests | Local MCP/Ollama bridge to query OpenLCA product systems and LCIA results. | [`openlca-mcp/README.md`](openlca-mcp/README.md) |
| `openLCA Automation/` | Prototype scripts | Tkinter and script-based OpenLCA automation for updating oil-pump energy values and running calculations. | [`openLCA Automation/README.md`](openLCA%20Automation/README.md) |
| `Machine Specific Scripts/` | Exploratory machine-data analysis | CNC and additive scripts for energy traces, feature-library inputs, and machine-specific plots. | [`Machine Specific Scripts/README.md`](Machine%20Specific%20Scripts/README.md) |
| `OpenNX Feature Library Draft/` | NX draft tool | NXOpen feature extraction and energy lookup prototype for CAD-phase machining energy estimation. | [`OpenNX Feature Library Draft/README.md`](OpenNX%20Feature%20Library%20Draft/README.md) |
| `Background watttime scripts/` | Legacy helpers | Early WattTime authentication, region, and location-test utilities. | [`Background watttime scripts/README.md`](Background%20watttime%20scripts/README.md) |

## Suggested reader paths

### If you are reviewing the research narrative

1. Read the repository map above.
2. Read the WattTime overview and the existing WattTime code guide.
3. Review the Chapter 3 runner scripts and generated summary markdown outputs.
4. Use the documentation roadmap to identify which missing methods, data, and figure-generation notes should be filled in before sharing externally.

### If you are trying to reproduce results

1. Start with the README for the relevant area.
2. Check whether the script depends on local absolute paths, private WattTime credentials, OpenLCA desktop state, Siemens NX, or large data files not committed to the repo.
3. Prefer the newer consolidated scripts and guides over versioned exploratory scripts unless you are intentionally tracing research history.
4. Record the exact data inputs, environment, and output folder in any new reproducibility notes.

### If you are improving the repo for future work

Use [`docs/DOCUMENTATION_ROADMAP.md`](docs/DOCUMENTATION_ROADMAP.md) for the documentation plan and [`docs/PROJECT_COMPLETION_CHECKLIST.md`](docs/PROJECT_COMPLETION_CHECKLIST.md) for the practical handoff checklist. Together, they separate quick wins from deeper cleanup so the archive can become a polished portfolio/research artifact without losing useful exploratory history.


## Handoff and cleanup docs

| Doc | Use it for |
| --- | --- |
| [`docs/RESEARCH_STORY.md`](docs/RESEARCH_STORY.md) | Plain-language narrative connecting machine energy, WattTime scheduling, NX features, and OpenLCA. |
| [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md) | Environment setup, external tool requirements, and runnable smoke checks. |
| [`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md) | What data is committed, private, generated, or still missing. |
| [`docs/CANONICAL_WORKFLOWS.md`](docs/CANONICAL_WORKFLOWS.md) | Preferred script paths versus exploratory/history scripts. |
| [`docs/FIGURE_INDEX.md`](docs/FIGURE_INDEX.md) | Trace thesis/report outputs back to scripts and inputs. |
| [`docs/SECURITY_AND_SHARING_CHECKLIST.md`](docs/SECURITY_AND_SHARING_CHECKLIST.md) | Steps to avoid exposing credentials, tokens, local paths, or private data. |
| [`docs/FUTURE_WORK.md`](docs/FUTURE_WORK.md) | Cleanup, research extensions, and portfolio polish ideas. |

## Important sharing and safety notes

- Treat this as a research workspace, not a clean software package yet.
- Rotate or remove any committed API tokens, passwords, machine IPs, UUIDs, or local paths before public release.
- Large generated outputs and local caches should be documented, but usually should not be committed unless they are curated summary artifacts.
- When adding new scripts, include a short header explaining purpose, inputs, outputs, dependencies, and whether the script is canonical or exploratory.

