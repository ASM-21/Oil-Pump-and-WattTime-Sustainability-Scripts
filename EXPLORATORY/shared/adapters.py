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

# The measurement data is now committed to the repo (Jul 2026 upload). CNC runs
# live in two sibling folders, AM prints in one. CNC_DATA_DIR / AM_DATA_DIR
# still override these when set, so external/local copies keep working.
_CNC_DIRS_IN_REPO = [_REPO_ROOT / "Al6061Body", _REPO_ROOT / "Al6061Lid"]
_AM_DIR_IN_REPO = _REPO_ROOT / "3D Printer Data"


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
# Local path config -- lets "press run" work without setting env vars each time
# ---------------------------------------------------------------------------

_DATA_CONFIG = _REPO_ROOT / "EXPLORATORY" / ".data_paths.txt"


def _read_config() -> dict[str, str]:
    """Read saved paths from .data_paths.txt (one KEY=value per line)."""
    if not _DATA_CONFIG.exists():
        return {}
    result = {}
    for line in _DATA_CONFIG.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _save_config(key: str, value: str) -> None:
    """Persist a single key=value to .data_paths.txt."""
    existing = _read_config()
    existing[key] = value
    lines = [f"{k}={v}" for k, v in existing.items()]
    _DATA_CONFIG.write_text("\n".join(lines) + "\n")


def _resolve_data_dir(env_var: str, description: str) -> str:
    """
    Resolve a data directory in this order:
      1. Environment variable (good for CI/scripting)
      2. Saved path in EXPLORATORY/.data_paths.txt (set on previous run)
      3. Interactive prompt (for press-to-run in an IDE)

    The chosen path is saved to .data_paths.txt so you only have to type it once.
    .data_paths.txt is gitignored (local machine paths don't belong in version control).
    """
    # 1. Environment variable
    val = os.environ.get(env_var, "").strip()
    if val and Path(val).exists():
        return val

    # 2. Saved config file
    saved = _read_config().get(env_var, "").strip()
    if saved and Path(saved).exists():
        print(f"[adapter] Using saved {env_var} = {saved}")
        return saved

    # 3. Interactive prompt -- works when you press Run in VS Code / PyCharm
    print()
    print(f"  {description}")
    print(f"  No path found for {env_var}.")
    print(f"  (You can also set it with:  export {env_var}=/your/path)")
    print()
    try:
        val = input("  Enter folder path: ").strip().strip('"').strip("'")
    except EOFError:
        # Non-interactive environment (CI, runner, agent): park instead of crash.
        raise DataNotInRepo(
            f"{env_var} is not set and no interactive prompt is available. "
            f"Set the environment variable and re-run."
        ) from None
    if not val:
        raise DataNotInRepo(
            f"{env_var} not configured and no path entered. "
            "Re-run and enter a valid path when prompted."
        )
    val = str(Path(val).expanduser().resolve())
    if not Path(val).exists():
        raise DataNotInRepo(
            f"Path {val!r} does not exist. Check the folder name and try again."
        )
    _save_config(env_var, val)
    print(f"  Saved to EXPLORATORY/.data_paths.txt -- won't ask again on this machine.")
    print()
    return val


def _resolve_cnc_dirs() -> list[Path]:
    """
    Resolve the CNC data director(ies), in priority order:
      1. CNC_DATA_DIR env var or saved config (a single external folder).
      2. The in-repo Al6061Body + Al6061Lid folders (data committed Jul 2026).
      3. Interactive prompt (single folder) as a last resort.

    Returns a LIST because the in-repo data is split across two sibling
    folders; callers iterate over it.
    """
    val = (os.environ.get("CNC_DATA_DIR", "").strip()
           or _read_config().get("CNC_DATA_DIR", "").strip())
    if val and Path(val).exists():
        return [Path(val)]

    in_repo = [d for d in _CNC_DIRS_IN_REPO if d.exists()]
    if in_repo:
        return in_repo

    return [Path(_resolve_data_dir(
        "CNC_DATA_DIR",
        "Folder containing your Al6061_body*.csv and Al6061_lid*.csv files from IN-MaC CNC runs.",
    ))]


def _cnc_csv_paths(dirs: list[Path], part: str | None = None,
                   run_id=None) -> list[Path]:
    """
    All Al6061 measurement CSVs across the given dirs, matching the optional
    part/run_id filter. Tolerant of zero-padded run numbers (body01 == body1)
    and case (AL6061 == Al6061). Excludes *error* files (malformed captures
    the analyzer would skip anyway) so raw re-parsing never trips on them.
    """
    import re as _re
    out = []
    for d in dirs:
        for path in sorted(d.glob("*.csv")):
            name = path.name
            if "error" in name.lower():
                continue
            m = _re.search(r"al6061_(lid|body)(\d+)_p(\d+)", name, _re.IGNORECASE)
            if not m:
                continue
            if part is not None and m.group(1).lower() != part:
                continue
            if run_id is not None and int(m.group(2)) != int(run_id):
                continue
            out.append(path)
    return out


# ---------------------------------------------------------------------------
# Public adapter functions
# ---------------------------------------------------------------------------

def load_operation_energy() -> pd.DataFrame:
    """
    Return the per-run, per-operation energy table for CNC machining.

    First run: prompts you to enter the folder containing your Al6061_*.csv files
    and saves the path for next time. Subsequent runs use the saved path automatically.

    You can also skip the prompt by setting the environment variable:
      export CNC_DATA_DIR=/path/to/your/csv/folder   (Mac/Linux)
      set    CNC_DATA_DIR=C:\\path\\to\\your\\csv\\folder  (Windows)

    Returns a DataFrame with the column contract in this module's docstring.
    Columns 'start', 'end', and 'peak_power_w' are NaT/NaN because the
    existing EnergyForFeatureLib loader does not expose per-operation timestamps
    or peak power. Available by re-parsing the raw 1 Hz stream via
    load_power_stream() if needed.
    """
    dirs = _resolve_cnc_dirs()
    if not _cnc_csv_paths(dirs):
        raise DataNotInRepo(
            f"No Al6061 CSV files found in {[str(d) for d in dirs]}.\n"
            "Check that you pointed at the right folder.\n"
            "To re-enter the path, delete EXPLORATORY/.data_paths.txt and re-run."
        )

    EnergyAnalyzer, clean_data = _import_energy_analyzer()

    # One analyzer instance accumulates results across folders (self.results
    # persists), so the final return carries every folder's rows.
    analyzer = EnergyAnalyzer()
    results_raw = validation = None
    for d in dirs:
        print(f"Loading CNC data from: {d}")
        results_raw, validation, _ = analyzer.analyze(str(d))

    if results_raw is None or results_raw.empty:
        raise DataNotInRepo(
            f"EnergyAnalyzer produced no results from {[str(d) for d in dirs]}. "
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

    # Active-power integration column (NaN when active power stream absent in CSV)
    if "Energy_Wh_Active" in cleaned.columns:
        df["energy_wh_active"] = cleaned["Energy_Wh_Active"].values
    else:
        df["energy_wh_active"] = float("nan")

    contract_cols = [
        "run_id", "part", "program", "operation_id", "operation_cat",
        "start", "end", "duration_s", "energy_wh", "energy_wh_active",
        "mean_power_w", "peak_power_w",
    ]
    return df[contract_cols].reset_index(drop=True)


def load_power_stream(run_id, part: str | None = None) -> pd.DataFrame:
    """
    Return the 1 Hz power stream for one run, with operation identity attached.

    Re-parses the raw Al6061_{part}{run_id}_p*.csv files from CNC_DATA_DIR and
    joins the interleaved processKindId / partKindId / active power rows on
    their shared timestamps, exactly as EnergyForFeatureLib.process_file does,
    but keeping every sample instead of integrating them away.

    Args:
      run_id: the part number from the filename (Part_Num in the energy table).
      part:   "body" or "lid". None loads both parts with that number.

    Returns one row per 1 Hz sample with columns:
      t             : pandas datetime
      power_w       : float
      operation_id  : decoded operation name ("NONE" while no operation active)
      program       : decoded program name ("NONE" outside any program)
      part          : "body" or "lid"
      source_file   : which raw CSV the sample came from

    Samples whose program decodes to UNKNOWN are kept and labeled, not dropped:
    signature work needs to see what attribution would discard.
    """
    import re as _re
    dirs = _resolve_cnc_dirs()
    frames = []
    EnergyAnalyzer, _ = _import_energy_analyzer()
    analyzer = EnergyAnalyzer()

    for path in _cnc_csv_paths(dirs, part=part, run_id=run_id):
        p = _re.search(r"al6061_(lid|body)", path.name, _re.IGNORECASE).group(1).lower()
        raw = pd.read_csv(path)
        streams = {}
        for name in ("processKindId", "partKindId", "active power"):
            s = raw[raw["Dataname"] == name][["Time", "Value"]].copy()
            # The logger emits wall-clock or elapsed time; the analyzer's
            # parser handles both. Reuse it so stream and energy agree.
            s["Time"] = analyzer._parse_time(s["Time"])
            streams[name] = s
        if any(s.empty for s in streams.values()):
            continue
        merged = (
            streams["processKindId"]
            .merge(streams["partKindId"], on="Time", suffixes=("_proc", "_part"))
            .merge(streams["active power"], on="Time")
        )
        merged.columns = ["t", "proc_uuid", "part_uuid", "power_w"]
        merged["power_w"] = pd.to_numeric(merged["power_w"], errors="coerce").clip(lower=0)
        merged = merged.sort_values("t").reset_index(drop=True)
        merged["operation_id"] = (
            merged["proc_uuid"].str.strip().str.upper()
            .map(lambda u: analyzer.uuid_to_operation.get(u, f"UNKNOWN_{str(u)[:8]}"))
        )
        merged["program"] = (
            merged["part_uuid"].str.strip().str.upper()
            .map(lambda u: analyzer.partkind_to_program.get(u, f"UNKNOWN_{str(u)[:8]}"))
        )
        merged["part"] = p
        merged["source_file"] = path.name
        frames.append(merged[
            ["t", "power_w", "operation_id", "program", "part", "source_file"]
        ])

    if not frames:
        raise DataNotInRepo(
            f"No Al6061 CSV files found for run_id={run_id!r}, part={part!r} "
            f"in {[str(d) for d in dirs]}. Check the run number and CNC_DATA_DIR."
        )
    return pd.concat(frames, ignore_index=True)


def list_run_ids(part: str | None = None) -> list[tuple[str, int]]:
    """
    Return the (part, run_id) pairs available across the CNC data dirs, from
    filenames alone (cheap; does not parse file contents). Zero-padding and
    case tolerant; excludes error files.
    """
    import re as _re
    found = set()
    for path in _cnc_csv_paths(_resolve_cnc_dirs(), part=part):
        m = _re.search(r"al6061_(lid|body)(\d+)_p(\d+)", path.name, _re.IGNORECASE)
        if m:
            found.add((m.group(1).lower(), int(m.group(2))))
    return sorted(found)


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


# ---------------------------------------------------------------------------
# AM (FDM printer) loaders
# ---------------------------------------------------------------------------
# The AM CSVs share the CNC files' long Time/Dataname/Value format but differ
# in two ways (per Machine Specific Scripts/Additive/*): the power metric is
# the literal 'power' (not 'active power'), and there is NO UUID interleave;
# each file is one print of one part. Filenames: {Prefix}_Part{N}.csv with
# Prefix in AM_PART_PREFIXES. Energy integration follows the boxplotter
# scripts: sort by time, dt from consecutive timestamps, drop the first
# sample, energy = sum(P * dt).

AM_PART_PREFIXES = ("DriveGear", "DriveShaft", "IdleGear", "IdleShaft")

# Ultimaker 2+ Extended rated power per GROUND_TRUTH.md. A quoted spec, not a
# measurement; A2_fdm_utilization verifies the measured draw against it.
AM_RATED_POWER_W = 221.0


def _am_data_dir() -> Path:
    """AM data folder: AM_DATA_DIR override, else the in-repo '3D Printer Data'."""
    val = (os.environ.get("AM_DATA_DIR", "").strip()
           or _read_config().get("AM_DATA_DIR", "").strip())
    if val and Path(val).exists():
        return Path(val)
    if _AM_DIR_IN_REPO.exists():
        return _AM_DIR_IN_REPO
    return Path(_resolve_data_dir(
        "AM_DATA_DIR",
        "Folder containing your FDM CSVs ({Prefix}_Part{N}.csv, "
        "Prefix in DriveGear/DriveShaft/IdleGear/IdleShaft).",
    ))


def list_am_run_ids(prefix: str | None = None) -> list[tuple[str, int]]:
    """
    (prefix, part_num) pairs available in the AM data dir, from filenames.

    The strict `_Part{N}.csv$` match naturally excludes annotated captures
    like 'DriveShaft_Part1 Broken sensor.csv' and '..._Part28 failed.csv';
    those excluded files are logged once so the drop is visible, not silent.
    """
    import re as _re
    found = set()
    excluded = []
    for path in _am_data_dir().glob("*_Part*.csv"):
        m = _re.match(r"(\w+)_Part(\d+)\.csv$", path.name)
        if m and m.group(1) in AM_PART_PREFIXES:
            found.add((m.group(1), int(m.group(2))))
        else:
            excluded.append(path.name)
    if excluded:
        print(f"[adapter] AM: excluded {len(excluded)} annotated/failed capture(s): "
              f"{sorted(excluded)}")
    pairs = sorted(found)
    if prefix:
        pairs = [p for p in pairs if p[0] == prefix]
    return pairs


def load_am_power_stream(prefix: str, part_num: int) -> pd.DataFrame:
    """
    One print's power samples: t, power_w, part, run_id, source_file.
    Raises DataNotInRepo if the file is absent.
    """
    path = _am_data_dir() / f"{prefix}_Part{part_num}.csv"
    if not path.exists():
        raise DataNotInRepo(
            f"AM file {path.name!r} not found in AM_DATA_DIR. "
            f"Available: {[f'{p}_Part{n}' for p, n in list_am_run_ids()]}"
        )
    raw = pd.read_csv(path)
    power = raw[raw["Dataname"] == "power"][["Time", "Value"]].copy()
    if power.empty:
        raise DataNotInRepo(
            f"No 'power' rows in {path.name}; Datanames present: "
            f"{sorted(raw['Dataname'].unique())}"
        )
    power["Time"] = pd.to_datetime(power["Time"], format="mixed")
    power = power.sort_values("Time").reset_index(drop=True)
    return pd.DataFrame({
        "t": power["Time"],
        "power_w": pd.to_numeric(power["Value"], errors="coerce").clip(lower=0),
        "part": prefix,
        "run_id": part_num,
        "source_file": path.name,
    })


def load_am_energy() -> pd.DataFrame:
    """
    Per-print energy table for every AM file in AM_DATA_DIR:
    part, run_id, energy_wh, duration_s, mean_power_w, peak_power_w.

    Integration matches the canonical boxplotter method: dt from consecutive
    timestamps, first sample dropped, energy = sum(P * dt).
    """
    pairs = list_am_run_ids()
    if not pairs:
        raise DataNotInRepo(
            "No {Prefix}_Part{N}.csv files found in AM_DATA_DIR. "
            "Expected prefixes: " + ", ".join(AM_PART_PREFIXES)
        )
    rows = []
    for prefix, num in pairs:
        s = load_am_power_stream(prefix, num)
        dt_h = s["t"].diff().dt.total_seconds() / 3600.0
        energy_wh = float((s["power_w"] * dt_h).iloc[1:].sum())
        duration_s = float((s["t"].iloc[-1] - s["t"].iloc[0]).total_seconds())
        rows.append({
            "part": prefix,
            "run_id": num,
            "energy_wh": energy_wh,
            "duration_s": duration_s,
            "mean_power_w": energy_wh * 3600.0 / duration_s if duration_s else float("nan"),
            "peak_power_w": float(s["power_w"].max()),
        })
    return pd.DataFrame(rows)


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
