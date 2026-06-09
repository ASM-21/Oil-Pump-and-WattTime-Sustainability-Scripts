# Canonical Workflows

This file identifies the preferred path through the repo today and separates it from exploratory history. It should be updated whenever scripts are renamed, archived, or replaced.

## 1. WattTime carbon-aware scheduling workflow

**Status:** closest to canonical; most developed research thread.

Preferred reading/run order:

1. `WattTime Analysis Folder/CODE_GUIDE.md`
2. `WattTime Analysis Folder/config.py`
3. `WattTime Analysis Folder/00_validate_data.py`
4. `WattTime Analysis Folder/01_data_collection v2.py`
5. `WattTime Analysis Folder/02_data_processing.py`
6. `WattTime Analysis Folder/ch3_common.py`
7. `WattTime Analysis Folder/ch3_run_all.py`
8. `WattTime Analysis Folder/ch3_run_all_extended.py`
9. `WattTime Analysis Folder/ch3_outputs/ch3_numbers.md`

Historical/exploratory scripts include multiple `03_temporal_patterns_*`, `06_heuristics_*`, and debug/one-off files. Keep them for provenance until the final thesis/paper figure index confirms which scripts are superseded.

## 2. Machine-energy-to-feature-library workflow

**Status:** exploratory but important for connecting measured energy to CAD/LCA.

Preferred current path:

1. Review `Machine Specific Scripts/README.md`.
2. Use CNC scripts for measured energy/program segmentation and additive scripts for 3D-printer energy summaries.
3. Curate feature-level energy values into the OpenNX feature library or OpenLCA oil-pump process assumptions.

Needed next: sample input schemas, units, and a canonical script list.

## 3. OpenNX CAD-phase energy estimation workflow

**Status:** prototype.

Preferred current path:

1. Open a part/assembly in Siemens NX.
2. Configure local paths in `OpenNX Feature Library Draft/main.py` or via future environment-variable refactor.
3. Run `main.py` through NX Open.
4. Review JSON/Excel reports and compare against measured CNC energy.

Needed next: sample output, validation notes, and environment-variable path support.

## 4. OpenLCA oil-pump update workflow

**Status:** prototype/local automation.

Preferred current path:

1. Open OpenLCA desktop and load the local oil-pump database.
2. Start IPC server.
3. Set `OPENLCA_SERVER_URL`, `OPENLCA_PROCESS_ID`, `OPENLCA_PRODUCT_SYSTEM_ID`, and `OPENLCA_LCIA_METHOD_ID` in local environment.
4. Run `openLCA Automation/update_static.py` for scripted updates or `update_gui.py` for GUI inspection.

Needed next: reference database name/version and expected smoke-test LCIA result.

## 5. OpenLCA MCP agent workflow

**Status:** separate prototype with tests.

Preferred current path:

1. Read `openlca-mcp/README.md`.
2. Install `openlca-mcp/requirements.txt` in a Python 3.11 environment.
3. Run pure validation tests first.
4. Start OpenLCA IPC and Ollama only for integration/agent tests.

## Deprecated or legacy areas

- `Background watttime scripts/` is retained for WattTime setup/reference utilities.
- Scripts with `debug`, `copy`, typo-heavy names, or version suffixes should be treated as provenance until archived or mapped in `docs/FIGURE_INDEX.md`.
