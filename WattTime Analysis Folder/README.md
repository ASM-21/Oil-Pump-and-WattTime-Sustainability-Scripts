# WattTime Analysis Folder

This folder is the main research workflow for carbon-aware manufacturing scheduling using WattTime grid-emissions signals. It includes the original numbered pipeline, Chapter 3 thesis scripts, supplemental analyses, generated summary markdown, and supporting utilities.

## Current status

**Most developed / closest to canonical.** The existing `CODE_GUIDE.md`, quick references, and Chapter 3 scripts make this the strongest starting point for understanding the research contribution.

## Research purpose

The scripts analyze when manufacturing jobs should be shifted within operational constraints to reduce emissions or health impacts. The work uses WattTime signals such as marginal operating emissions rate, average operating emissions rate, and health-damage estimates to compare baseline operation against carbon-aware scheduling decisions.

## How the folder is organized

| Group | Files | Role |
| --- | --- | --- |
| Core configuration/utilities | `config.py`, `utils/` | Shared credentials/settings, data-library management, API helpers, run-folder setup, validation helpers. |
| Numbered pipeline | `00_validate_data.py` through `13_grafana_operator_deploy.py` | Sequential workflow for collection, processing, temporal analysis, scheduling simulation, forecasting, heuristics, and operator-facing outputs. |
| Chapter 3 scripts | `ch3_*.py`, `CH3_FIG_*.py`, `Ch3*.py` | More focused thesis/report analyses and figure/table generation. |
| Extended analyses | `ch3_extended_*.py`, `ch3_run_all_extended.py` | Deeper sensitivity, economics, health co-benefits, portability, and production-queue analyses. |
| Supplemental scripts | `ch3_supp_*.py`, `ch3_appendix_c.py` | Appendix and robustness analyses. |
| Generated summaries | `ch3_outputs/*.md`, `ch3_supp_numbers.md`, `data_validation_report.md` | Human-readable summary outputs from analysis runs. |
| Existing guides | `CODE_GUIDE.md`, `watttime_quick_reference.md`, `watttime_heuristic_tool_guide.md`, `old readme.md` | Prior handoff/reference documentation. |

## Suggested reading order

1. `CODE_GUIDE.md` for the broad code inventory and handoff notes.
2. `watttime_quick_reference.md` for quick command/script reminders.
3. `ch3_common.py` to understand shared Chapter 3 calculations.
4. `ch3_run_all.py` and `ch3_run_all_extended.py` to see the thesis workflow orchestration.
5. `ch3_outputs/ch3_numbers.md` and `ch3_outputs/ch3_numbers_extended.md` for generated summary results.

## Reproducibility notes to fill in

- Location of the local WattTime data library and run folders.
- Required Python version and package list.
- Which script versions are canonical when multiple `v1`/`v2`/`v3` files exist.
- Exact commands used to regenerate thesis figures and summary markdown.
- Which outputs are generated artifacts versus hand-written interpretation.

## Safety notes before sharing

- Move WattTime credentials into environment variables or a local ignored config file.
- Remove private API tokens, license-dependent data paths, and large cached datasets from public commits.
- Clearly document any data that cannot be redistributed under the WattTime license.

