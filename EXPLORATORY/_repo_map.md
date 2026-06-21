# Repo map: discovery findings

This file records what was found during the discovery pass (AGENT_BRIEF section 0).
It is the single place that documents how the existing repo exposes its data, so the
adapter implementation can be understood and updated if the repo moves.

---

## Per-operation energy table (primary source -- blocks everything)

**Location:** `Machine Specific Scripts/CNC/EnergyForFeatureLib.py`
**Class:** `EnergyAnalyzer`
**Entry point:** `EnergyAnalyzer().analyze(directory)` -- returns `(results, validation, quality)`

**Data source:** CSV files named `Al6061_(body|lid)<N>_p<M>.csv` in a user-supplied directory.
These files are NOT committed to this repo (see `docs/DATA_INVENTORY.md`).
Must be supplied via `CNC_DATA_DIR` environment variable.

**CSV format:**
```
Time,Dataname,Value
2024-...,processKindId,<operation-UUID>
2024-...,partKindId,<program-UUID>
2024-...,active power,<watts>
```
All three Dataname types appear at the same timestamps (1 Hz).

**What `analyze()` returns (results DataFrame columns):**
```
Part_Type     : str  ("Body" or "Lid" -- note uppercase)
Part_Num      : int  (from filename, e.g. body3 -> 3)
Program       : str  ("PROGRAM_1_Body", "PROGRAM_2_Body", ..., "PROGRAM_1_Lid", "PROGRAM_2_Lid")
Operation     : str  (decoded from UUID, e.g. "CAVITY_MILL_OUTSIDE")
Energy_Wh     : float
Duration_Sec  : float
Avg_Power_W   : float
Data_Points   : int
Segments      : int
```

**Cleaning step:** `clean_data(results, validation)` removes:
- Body Part 17 (missing operations)
- Operations starting with "UNKNOWN" (UUID not in mapping)
- Records with insufficient data points for specific short operations
- Statistical outliers (>2.5 std dev; flagged as Is_Outlier, not removed)

---

## Operation identity

**Keying:** Operations are identified by UUID in the raw data. The adapter decodes UUIDs to
stable string names using the hardcoded mapping in `EnergyForFeatureLib.py`.

**Taxonomy reconciliation (45 vs 49 discrepancy):**
- Body operations in UUID map: 31 distinct operations
- Lid operations in UUID map: 14 distinct operations
- Total distinct operation names: 45

The "49" count likely comes from counting per-program rather than per-name:
some operations (e.g. FACE_TOP_PLANE, PLANAR_PROFILING_AGAIN) appear in multiple
body programs with the same UUID, so they count as 1 operation but appear across 4 programs.
The adapter's `operation_id` column uses the decoded name (45 distinct values).
Verify by running `shared/test_adapters.py` -- it prints `ops=N` after loading.

**UUID-to-operation mapping:** hardcoded in `EnergyForFeatureLib.py` lines ~32-79.
Same mapping (slightly expanded) in `EnergyForFeatureLib_otherValsV2.py` with archetype
classification. The adapter imports from `EnergyForFeatureLib` (the canonical source).

**Program UUIDs (partKindId -> program name):**
```
5BC675E0-...  -> NONE (idle / between programs)
072B393C-...  -> PROGRAM_1_Body
EDB34637-...  -> PROGRAM_2_Body
5E4A09CE-...  -> PROGRAM_3_Body
D2C78EB3-...  -> PROGRAM_4_Body
68C62535-...  -> PROGRAM_1_Lid
7606F116-...  -> PROGRAM_2_Lid
```

---

## Raw 1 Hz power streams

**Location:** Same CSV files as above (each file = one physical run).
**Access:** The existing `EnergyAnalyzer` processes these files but does not expose the
raw per-sample stream at the adapter level. To get the 1 Hz stream for a specific run,
parse the CSV directly (filter `Dataname == 'active power'`) and join with the UUID log.

`load_power_stream()` in `adapters.py` raises `DataNotInRepo` as a reminder to implement
this when needed. The raw data is there; the join is not yet wired.

---

## AM (FDM) data

**Location:** CSV files in a separate directory (not committed). Hardcoded Windows path
in `Machine Specific Scripts/Additive/3dPrinter_V1.py`:
`C:\Users\Administrator\OneDrive...\DriveShaft_Part16.csv`

**Same CSV format** as CNC files (`Time`, `Dataname`, `Value`).
Must be supplied via `AM_DATA_DIR` environment variable (not yet wired in adapters.py).

**FDM spec:** Ultimaker 2+ Extended, rated 221 W, measured ~200 W draw.

---

## BOM / part masses

**Not committed as structured data.** Context doc estimates exist (unverified):
- Body: 1,437 g mass removed (from SCOPE_tier_A_B_C.md)
- Lid: 448 g mass removed

To supply: create `EXPLORATORY/bom.csv` (see template in `bom_template.csv` or
`_data_gaps.md`). `load_bom()` checks for this file automatically.

---

## WattTime MOER data

**Not committed.** WattTime raw/historical signals live locally (not in repo).
See `WattTime Analysis Folder/` for scripts that collected and processed them.
`load_moer()` returns `None` until `moer.parquet` or `moer.csv` is placed in
`WattTime Analysis Folder/`. The `emission_factors/` project parks on None.

---

## OpenLCA integration

**Location:** `openLCA Automation/`, `openlca-mcp/`
**Not used by EXPLORATORY projects.** The LCA processing pipeline is separate from
the per-operation energy attribution. Not wired into adapters.py.

---

## Existing analysis scripts (read-only reference)

| Script | What it does |
|---|---|
| `Machine Specific Scripts/CNC/EnergyForFeatureLib.py` | Primary data source -- adapter imports from here |
| `Machine Specific Scripts/CNC/EnergyForFeatureLib_otherValsV2.py` | Expanded archetype classification; useful reference for operation taxonomy |
| `Machine Specific Scripts/CNC/Map8_CNC_UUIDSvsCSV.py` | Per-file UUID/program energy breakdown; useful for debugging |
| `Machine Specific Scripts/CNC/map8CNCtotals_BoxplotsPROGREAM_upgradFigures.py` | Program-level boxplots (paper figures) |
| `Machine Specific Scripts/Additive/3dPrinter_V1.py` | FDM data visualization; shows same CSV format |
| `OpenNX Feature Library Draft/` | CAM-level feature energy library; relevant for feature_energy/ if built |
| `WattTime Analysis Folder/ch3_*.py` | Chapter 3 scheduling analysis; separate from EXPLORATORY |

---

## Key numbers from data (to verify once CNC_DATA_DIR is set)

Run `python EXPLORATORY/shared/test_adapters.py` and record the printed values here:

| Quantity | Expected | Computed | Date |
|---|---|---|---|
| Distinct operation names (ops=) | 45 | TODO | - |
| Unique runs per program | 16-27 | TODO | - |
| Parts loaded | body + lid | TODO | - |
