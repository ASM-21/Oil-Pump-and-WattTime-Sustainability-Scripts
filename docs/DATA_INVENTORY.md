# Data Inventory

This inventory distinguishes committed reference artifacts from local/private data needed to reproduce results. Keep this file updated when adding datasets, generated outputs, or sample data.

| Dataset/artifact | Used by | Format | Committed? | Source/access | Notes |
| --- | --- | --- | --- | --- | --- |
| WattTime region availability | Background WattTime helpers | CSV | Yes: `Background watttime scripts/watttime_regions.csv` | WattTime API/account access | Reference export of accessible regions/signals; confirm redistribution terms before public release. |
| WattTime raw/historical signal library | WattTime analysis | Parquet/CSV, local cache | No | WattTime API | Needed for collection/processing/Chapter 3 reruns. Store under a local ignored directory. |
| WattTime run outputs | WattTime analysis | CSV/Parquet/figures/markdown | Partial | Generated locally | Summary markdown is committed; full run folders should be documented before committing. |
| Chapter 3 summary numbers | WattTime analysis | Markdown | Yes: `WattTime Analysis Folder/ch3_outputs/` and `ch3_supp_numbers.md` | Generated from analysis scripts | Treat as current summary artifacts, but add figure/table traceability before publication. |
| Machine energy traces | Machine-specific scripts | CSV/Excel exports | No/unknown | Lab machine data exports | Add anonymized samples with units, sampling rate, and program identifiers. |
| CNC UUID/program mapping | Machine-specific scripts | Embedded mappings in scripts | Yes | Derived from lab/OpenLCA/machine identifiers | Review UUID sensitivity before public release. |
| OpenNX aluminum feature library | OpenNX draft | XLSX | Yes: `OpenNX Feature Library Draft/aluminum_expanded.xlsx` | Derived feature-energy library | Document units, source measurements, and validation coverage. |
| OpenLCA oil-pump database | OpenLCA automation and MCP | OpenLCA database | No | Local OpenLCA desktop database | Needs database name/version and shareability decision. |
| OpenLCA MCP logs | openlca-mcp | JSONL/log | No | Generated locally | Ignored by `.gitignore`; do not commit routine logs. |

## Data to add for handoff

- A tiny anonymized WattTime-like sample file for parser/smoke tests.
- A tiny anonymized machine-energy CSV with documented columns and units.
- A sample OpenLCA result JSON/CSV that does not require sharing the database.
- A sample OpenNX report output generated from a non-sensitive part.
