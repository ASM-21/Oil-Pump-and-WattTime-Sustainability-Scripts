# Reproducibility Guide

This repository combines plain Python analysis, API-backed data collection, Siemens NX automation, OpenLCA desktop automation, and a local OpenLCA MCP prototype. Not every workflow can run from a fresh clone because some data and desktop software are private or licensed.

## Baseline Python setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For the OpenLCA MCP prototype, use the folder-specific requirements too:

```bash
cd openlca-mcp
pip install -r requirements.txt
```

## Environment variables

Copy `.env.example` to `.env` and set the variables relevant to the workflow you are running. Python scripts in this repo do not automatically load `.env`; either export variables in your shell or use your preferred dotenv workflow.

Key variables:

| Variable | Used by | Purpose |
| --- | --- | --- |
| `WATTTIME_USERNAME` / `WATTTIME_PASSWORD` | WattTime scripts | API authentication. |
| `WATTTIME_LIBRARY_DIR` / `WATTTIME_RUNS_DIR` | WattTime analysis | Local data/cache locations. |
| `OPENLCA_SERVER_URL` | OpenLCA automation | IPC server URL, usually localhost for a local desktop session. |
| `OPENLCA_PROCESS_ID` | OpenLCA automation | Local process UUID for the oil-pump model. |
| `OPENLCA_PRODUCT_SYSTEM_ID` / `OPENLCA_LCIA_METHOD_ID` | OpenLCA automation | Product system and LCIA method for calculations. |
| `OPENNX_MATERIAL_LIBRARY` / `OPENNX_OUTPUT_DIR` | OpenNX draft | Local NX material library and report output paths. |

## Workflow reproducibility status

| Workflow | Can run from fresh clone? | Extra requirements | Notes |
| --- | --- | --- | --- |
| Documentation checks | Yes | Python standard library | See `tests/test_repository_hygiene.py`. |
| OpenLCA MCP validation unit tests | Mostly | `openlca-mcp/requirements.txt` | Pure validation tests do not require OpenLCA; integration tests skip or fail depending on IPC availability. |
| WattTime data collection | No | WattTime account, valid API access, local data library path | Data redistribution may be restricted. |
| WattTime Chapter 3 analysis | Partial | Existing processed WattTime library/run folders | Needs canonical input/output paths documented in `docs/DATA_INVENTORY.md`. |
| Machine-specific scripts | Partial | Lab exports or sample data | Add anonymized example data before expecting external reproducibility. |
| OpenNX feature extraction | No | Siemens NX/NXOpen and local part files | Run inside NX, not a normal terminal. |
| OpenLCA automation GUI/static updater | No | OpenLCA desktop, database, IPC server, UUIDs | Configure via `.env`. |

## Suggested smoke checks

```bash
python -m pytest tests/test_repository_hygiene.py
python -m pytest openlca-mcp/tests/test_validation.py
```

The first command is a lightweight repo-health check. The second validates the MCP argument-validation layer and should not need OpenLCA IPC.
