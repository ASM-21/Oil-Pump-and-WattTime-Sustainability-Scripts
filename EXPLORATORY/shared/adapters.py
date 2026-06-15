"""
Adapter layer between EXPLORATORY projects and the repo's existing data access.

WHY THIS EXISTS
Projects must not reparse raw data or hardcode paths. They import from here, and
here is the ONE place that knows how the existing repo exposes its data.

HOW TO USE (IMPORTANT - READ BEFORE RUNNING ANY PROJECT)
The raw CNC measurement CSVs are NOT committed to this repo. You must point
the adapter at your local copy of the data using an environment variable:

    export CNC_DATA_DIR=/path/to/your/Al6061_csv_files

On Windows:
    set CNC_DATA_DIR=C:\\Users\\you\\path\\to\\data

The folder you point to should contain files named like:
    Al6061_body1_p1.csv, Al6061_body2_p1.csv, ..., Al6061_lid1_p1.csv, ...

If CNC_DATA_DIR is not set, every project will park itself and explain what
you need to do. Set it and re-run.

For the AM (FDM) data, set AM_DATA_DIR similarly:
    export AM_DATA_DIR=/path/to/your/am_csv_files

CONTRACT each function must satisfy (do not change the signatures or returned
column names; projects depend on them):

  load_operation_energy() -> DataFrame with at least:
      run_id        : int, unique per physical part run (Part_Num from CSV filename)
      part          : str, "body", "lid", or "am_<name>"
      program       : str, e.g. "PROGRAM_1_Body"
      operation_id  : str, the decoded operation name (stable key from UUID map)
      operation_cat : str, category from the canonical taxonomy below
      start, end    : pandas datetime (NaT if not available from existing loader)
      duration_s    : float
      energy_wh     : float
      mean_power_w  : float
      peak_power_w  : float (NaN if not available from existing loader)

  load_power_stream(run_id) -> DataFrame with:
      t             : pandas datetime (1 Hz)
      power_w       : float
      operation_id  : str or NaN

  load_program_table() -> DataFrame: program structure + mean durations
  load_bom()           -> DataFrame: bill of materials incl. masses if present
  load_moer()          -> DataFrame or None: WattTime MOER if co-located in repo

Absent required source -> raises DataNotInRepo. Optional source (MOER) -> None.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
import pandas as pd

# Path to repo root (two levels up from this file)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CNC_SCRIPTS = _REPO_ROOT / "Machine Specific Scripts" / "CNC"


class DataNotInRepo(FileNotFoundError):
    """Raised when a required dataset is not present in the repository."""


# ---------------------------------------------------------------------------
# Canonical operation taxonomy
# ---------------------------------------------------------------------------
OPERATION_CATEGORIES = [
    "cavity_milling",
    "face_milling",
    "finishing",
    "drilling",
    "spotting",
    "tapping",
    "profiling",
    "engraving",
    "homing",      # non-productive repositioning (TRANSITION_OVERHEAD in raw data)
    "idle",        # NONE_IDLE in raw data
    "am_print",
]

# High-variability categories expected from paper (verify from data)
HIGH_VARIABILITY = {"spotting", "tapping", "drilling", "profiling", "engraving"}

# Maps decoded operation names from EnergyForFeatureLib to canonical categories.
# Body operations: 31 total. Lid operations: 14 total. Total distinct: 45.
_OP_TO_CATEGORY: dict[str, str] = {
    # Rough/cavity milling
    "CAVITY_MILL_OUTSIDE":          "cavity_milling",
    "CAVITY_MILL_INSIDE":           "cavity_milling",
    "LID_CAVITY_MILL":              "cavity_milling",
    "LID_POCKETING":                "cavity_milling",
    # Face milling / facing
    "FACE_DATUM_A":                 "face_milling",
    "FACE_TOP_PLANE":               "face_milling",
    "FACE_TOP_PLANE_COPY":          "face_milling",
    "FLOOR_FACING":                 "face_milling",
    "LID_FLOOR_FACING":             "face_milling",
    "LID_FINISH_FACE":              "face_milling",
    # Finishing (contour/wall/profile passes)
    "FINISH_OUTER_WALL":            "finishing",
    "FINISH_OUTER_PROFILE":         "finishing",
    "FINISH_INNER_PROFILE":         "finishing",
    "FINISH_POCKET_HOLE":           "finishing",
    "FINISH_CBORE":                 "finishing",
    "LID_FINISH_SURFACES":          "finishing",
    "LID_FINISH_UPPER_WALL":        "finishing",
    "LID_FINISH_OUTER_PROFILE":     "finishing",
    "LID_CHAMFER_EDGES":            "finishing",
    "LID_CHAMFER_EDGES_AGAIN":      "finishing",
    "LID_HOLE_MILLING":             "finishing",
    # Profiling / deburring
    "WALL_FLOOR_PROFILING":         "profiling",
    "PLANAR_PROFILING_AGAIN":       "profiling",
    "PLANAR_PROFILING_AGAIN_COPY":  "profiling",
    "PLANAR_DEBURRING":             "profiling",
    # Spotting
    "SPOTTING_LID_HOLES":           "spotting",
    "SPOTTING_LH":                  "spotting",
    "SPOTTING_CBORE":               "spotting",
    "SPOTTING_POCKET_HOLE":         "spotting",
    "SPOTTING_NPT_TOP":             "spotting",
    "SPOTTING_NPT_BOTTOM":          "spotting",
    "LID_SPOTTING_HOLES":           "spotting",
    "LID_SPOTTING_SHAFT_HOLES":     "spotting",
    # Drilling
    "DRILLING_LID_HOLES":           "drilling",
    "DRILLING_LH":                  "drilling",
    "DRILLING_POCKET_HOLE":         "drilling",
    "DRILLING_CBORE":               "drilling",
    "DRILLING_NPT_TOP":             "drilling",
    "DRILLING_NPT_BOTTOM":          "drilling",
    "LID_DRILLING_HOLES":           "drilling",
    "LID_DRILLING_SHAFT_HOLES":     "drilling",
    # Tapping
    "TAPPING_LID_HOLES":            "tapping",
    "TAPPING_NPT_TOP":              "tapping",
    "TAPPING_NPT_BOTTOM":           "tapping",
    # Engraving
    "ENGRAVING":                    "engraving",
    # Idle / overhead (non-productive)
    "NONE_IDLE":                    "idle",
    "TRANSITION_OVERHEAD":          "homing",  # repositioning between operations
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _import_energy_analyzer():
    """Import EnergyAnalyzer and clean_data from the existing CNC script."""
    if str(_CNC_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_CNC_SCRIPTS))
    try:
        from EnergyForFeatureLib import EnergyAnalyzer, clean_data  # noqa: PLC0415
        return EnergyAnalyzer, clean_data
    except ImportError as exc:
        raise DataNotInRepo(
            f"Could not import EnergyForFeatureLib from {_CNC_SCRIPTS}. "
            f"Check that the repo structure is intact. Original error: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Public adapter functions
# ---------------------------------------------------------------------------

def load_operation_energy() -> pd.DataFrame:
    """
    Return the per-run, per-operation energy table for CNC machining.

    Reads from CNC_DATA_DIR (environment variable). Raises DataNotInRepo
    with setup instructions if the variable is not set or the directory is
    missing/empty.

    Returns a DataFrame with the column contract in this module's docstring.
    Columns 'start', 'end', and 'peak_power_w' are NaT/NaN because the
    existing EnergyForFeatureLib loader does not expose per-operation timestamps
    or peak power. They are available by re-parsing the raw 1 Hz stream via
    load_power_stream() if needed.
    """
    data_dir = os.environ.get("CNC_DATA_DIR", "").strip()
    if not data_dir:
        raise DataNotInRepo(
            "\n"
            "CNC_DATA_DIR is not set. Before running any project, do:\n"
            "\n"
            "  Linux/Mac:  export CNC_DATA_DIR=/path/to/your/csv/folder\n"
            "  Windows:    set CNC_DATA_DIR=C:\\path\\to\\your\\csv\\folder\n"
            "\n"
            "The folder must contain your Al6061_body*.csv and Al6061_lid*.csv\n"
            "measurement files from the IN-MaC CNC runs.\n"
        )

    data_path = Path(data_dir)
    if not data_path.exists():
        raise DataNotInRepo(
            f"CNC_DATA_DIR={data_dir!r} does not exist on this machine.\n"
            "Update the environment variable to point at your local data folder."
        )

    csv_files = list(data_path.glob("Al6061_*.csv"))
    if not csv_files:
        raise DataNotInRepo(
            f"No Al6061_*.csv files found in CNC_DATA_DIR={data_dir!r}.\n"
            "Check that you pointed at the right folder."
        )

    EnergyAnalyzer, clean_data = _import_energy_analyzer()

    print(f"Loading CNC data from: {data_path}")
    analyzer = EnergyAnalyzer()
    results_raw, validation, _ = analyzer.analyze(str(data_path))

    if results_raw is None or results_raw.empty:
        raise DataNotInRepo(
            f"EnergyAnalyzer produced no results from {data_dir!r}. "
            "Check that the CSV files match the expected naming convention."
        )

    cleaned, _ = clean_data(results_raw, validation)

    if cleaned is None or cleaned.empty:
        raise DataNotInRepo("All rows were removed during data cleaning. Check your CSV files.")

    # Map to contract column names
    df = cleaned.rename(columns={
        "Part_Num":    "run_id",
        "Program":     "program",
        "Operation":   "operation_id",
        "Energy_Wh":   "energy_wh",
        "Duration_Sec": "duration_s",
        "Avg_Power_W": "mean_power_w",
    }).copy()

    df["part"] = cleaned["Part_Type"].str.lower()
    df["operation_cat"] = df["operation_id"].map(_OP_TO_CATEGORY)

    # Flag any operations not in the taxonomy so you notice them
    unknown_cats = df["operation_cat"].isna()
    if unknown_cats.any():
        unknown_ops = df.loc[unknown_cats, "operation_id"].unique().tolist()
        print(f"WARNING: {len(unknown_ops)} operation(s) have no category mapping "
              f"and will be labeled 'unknown': {unknown_ops}")
    df["operation_cat"] = df["operation_cat"].fillna("unknown")

    # These columns are not available from the existing level of processing
    df["start"] = pd.NaT
    df["end"] = pd.NaT
    df["peak_power_w"] = float("nan")

    contract_cols = [
        "run_id", "part", "program", "operation_id", "operation_cat",
        "start", "end", "duration_s", "energy_wh", "mean_power_w", "peak_power_w",
    ]
    return df[contract_cols].reset_index(drop=True)


def load_power_stream(run_id) -> pd.DataFrame:
    """
    Return the 1 Hz power stream for one run, with operation identity attached.

    NOT IMPLEMENTED: the existing EnergyForFeatureLib loader does not expose the
    raw per-sample stream. Implementing this requires re-parsing the raw CSV for
    the given run_id and joining the UUID event log -- straightforward but not
    yet wired here.

    Projects that need this (disaggregation, feature_energy) should either
    implement it here or park themselves with DataNotInRepo.
    """
    raise DataNotInRepo(
        "load_power_stream() is not yet implemented. "
        "It needs to re-parse the raw 1 Hz CSV and join UUID event logs. "
        "Add the implementation here and set CNC_DATA_DIR to your data folder."
    )


def load_program_table() -> pd.DataFrame:
    """
    Return program structure and mean durations, derived from the operation table.

    Calls load_operation_energy() internally; requires CNC_DATA_DIR to be set.
    """
    df = load_operation_energy()
    prog = df.groupby(["part", "program"]).agg(
        n_operations=("operation_id", "nunique"),
        n_runs=("run_id", "nunique"),
        mean_duration_s=("duration_s", "mean"),
        total_duration_s=("duration_s", "sum"),
        mean_energy_wh=("energy_wh", "mean"),
    ).reset_index()
    return prog


def load_bom() -> pd.DataFrame:
    """
    Return bill of materials including part masses.

    NOT IN REPO: Stock and finished masses are not committed as structured data.
    The context docs quote 1,437 g body and 448 g lid removed, but these need
    verification against your actual measurement records before use in the paper.

    To unpark projects that need this, either:
    (a) Add a bom.csv to EXPLORATORY/ with columns:
        part, stock_mass_g, finished_mass_g, mass_removed_g
    (b) Or hard-code verified values in the project that needs them.
    """
    bom_path = _REPO_ROOT / "EXPLORATORY" / "bom.csv"
    if bom_path.exists():
        return pd.read_csv(bom_path)
    raise DataNotInRepo(
        "BOM/mass data is not in this repo. Stock and finished masses were not "
        "committed. To fix this:\n"
        "  1. Verify stock and finished masses from your lab records.\n"
        "  2. Create EXPLORATORY/bom.csv with columns:\n"
        "     part, stock_mass_g, finished_mass_g, mass_removed_g\n"
        "  3. Re-run the project.\n"
        "Context doc estimate (unverified): body 1437 g removed, lid 448 g removed."
    )


def load_moer() -> pd.DataFrame | None:
    """
    Return WattTime MOER data if it is co-located in this repo, else None.

    The WattTime parquet files are not committed (see DATA_INVENTORY.md).
    emission_factors/ will park itself when this returns None.
    """
    moer_candidates = [
        _REPO_ROOT / "WattTime Analysis Folder" / "moer.parquet",
        _REPO_ROOT / "WattTime Analysis Folder" / "moer.csv",
    ]
    for path in moer_candidates:
        if path.exists():
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path)
    # WattTime raw data is not committed; emission_factors parks itself on None
    return None
