# Data gaps

Projects that cannot run append their gap here automatically.
Each gap records what is missing and what you need to supply to unpark the project.

---

## RESOLVED 2026-07-09: BOM / part masses

`EXPLORATORY/bom.csv` is now committed with owner-verified masses
(body 1880/443/1437 g, lid 518/70/448 g). `load_bom()` returns it; the
L2 estimation, allocation mass rule, and specific-energy calculations are
unblocked. The CNC measurement CSVs (below) are now the ONLY blocking gap
for the remaining projects. Note the new projects (theory/, signature_mining,
energy_budget, uncertainty_prediction) do not park on it: they verify
themselves on synthetic fixtures (`shared/fixtures.py`) and add measured
tables when the CSVs arrive.

---

## CNC raw measurement CSVs (blocks all CNC projects)

**Required for:** estimation_ladder, allocation, wear_runorder, all future CNC projects.

**What is missing:** The Al6061_body*.csv and Al6061_lid*.csv measurement files
from the IN-MaC CNC runs are not committed to this repo (see docs/DATA_INVENTORY.md).

**How to fix:**
Set the CNC_DATA_DIR environment variable to point at your local folder:

    Linux/Mac:  export CNC_DATA_DIR=/path/to/your/csv/folder
    Windows:    set CNC_DATA_DIR=C:\path\to\your\csv\folder

The folder should contain files named like Al6061_body1_p1.csv, Al6061_lid3_p2.csv, etc.

---

## BOM / part masses (blocks L2 estimation and specific-energy calculations)

**Required for:** estimation_ladder (L2 SEC estimate), allocation (mass-based rule),
any per-kg-removed energy calculation.

**What is missing:** Stock and finished masses are not committed as structured data.
Context doc estimates exist (body 1437 g removed, lid 448 g removed) but these
need verification against actual measurement records before use in the paper.

**How to fix:**
Create EXPLORATORY/bom.csv with the following columns and one row per part:

    part, stock_mass_g, finished_mass_g, mass_removed_g

Example:
    body, 2500.0, 1063.0, 1437.0
    lid,  610.0,  162.0,  448.0

Once this file exists, load_bom() will return it and L2/allocation will be fully enabled.

---

## WattTime MOER data (blocks emission_factors project)

**Required for:** emission_factors (not currently being built).

**What is missing:** moer.parquet or moer.csv is not in the WattTime Analysis Folder/.
The WattTime raw data is stored locally and not committed (see docs/DATA_INVENTORY.md).

**How to fix (when emission_factors is built):**
Copy or symlink your WattTime MOER parquet to:
    WattTime Analysis Folder/moer.parquet

Expected columns: timestamp (UTC), moer_lbs_per_mwh (or equivalent), region.

---

## AM (FDM) measurement data (partially blocks the FDM side)

**Required for:** computing u_FDM from data instead of the spec sheet
(explorations/A2_fdm_utilization.py), future disaggregation projects.

**What is missing:** The FDM CSV files ({Prefix}_Part{N}.csv, Prefix in
DriveGear/DriveShaft/IdleGear/IdleShaft) are not in this repo.

**Status 2026-07-09:** `load_am_energy()` and `load_am_power_stream()` are now
implemented in EXPLORATORY/shared/adapters.py (power key 'power', boxplotter
integration rule) and are fixture-verified. Until AM_DATA_DIR is set, u_FDM
stays a spec-sheet number (~0.90).

**How to fix:**
Set AM_DATA_DIR to your local FDM CSV folder and run:

    python EXPLORATORY/explorations/A2_fdm_utilization.py

---
