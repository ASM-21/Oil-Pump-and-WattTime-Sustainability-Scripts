"""
Build _summary.md from project output CSVs.

Run this AFTER estimation_ladder and allocation have produced their outputs:
    python EXPLORATORY/build_summary.py

What it does:
  1. Reads output CSVs from each project (skips gracefully if not yet generated).
  2. Fills in the key-numbers table with computed values.
  3. Flags every quoted-vs-computed disagreement found across all FINDINGS files.
  4. Writes EXPLORATORY/_summary.md.

Status codes:
  [built]    -- project ran, outputs exist, numbers filled in
  [parked]   -- project ran but data was unavailable (DataNotInRepo)
  [missing]  -- outputs directory doesn't exist yet (project not run)
  [explored] -- desk-note only, no build outputs
"""

from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPLORATORY = Path(__file__).parent

sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_csv_safe(path: Path) -> pd.DataFrame | None:
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception as e:
            print(f"  WARNING: could not read {path.name}: {e}")
    return None


def _project_status(name: str) -> str:
    out_dir = EXPLORATORY / name / "outputs"
    findings = EXPLORATORY / name / "FINDINGS.md"
    if not out_dir.exists():
        return "missing"
    csvs = list(out_dir.glob("*.csv"))
    if not csvs and findings.exists():
        return "parked"
    if csvs:
        return "built"
    return "parked"


# ---------------------------------------------------------------------------
# Pull numbers from estimation_ladder outputs
# ---------------------------------------------------------------------------

def _ladder_numbers() -> dict:
    out = EXPLORATORY / "estimation_ladder" / "outputs"
    nums: dict = {}

    summary = _read_csv_safe(out / "summary_by_part.csv")
    if summary is not None:
        for _, row in summary.iterrows():
            p = row.get("part", "")
            nums[f"{p}_L4_mean_wh"] = row.get("L4_mean_wh")
            nums[f"u_cnc"] = row.get("u_cnc")
            nums[f"u_fdm"] = row.get("u_fdm")
            nums[f"{p}_L0_error_pct"] = row.get("L0_mean_error_pct")
            nums[f"{p}_L1_error_pct"] = row.get("L1_mean_error_pct")
            nums[f"{p}_L2_error_pct"] = row.get("L2_mean_error_pct")

    norm = _read_csv_safe(out / "normality_shapiro_wilk.csv")
    if norm is not None:
        nums["n_near_normal"] = int(norm["near_normal"].sum())
        nums["n_sw_tested"] = len(norm)

    pv = _read_csv_safe(out / "uncertainty_intervals.csv")
    if pv is not None:
        nums["max_cv_pct"] = float(pv["cv_pct"].max())
        nums["mean_ci_95_pct"] = float(pv["ci_95_pct"].mean())
        nums["prog_var_df"] = pv

    return nums


# ---------------------------------------------------------------------------
# Pull numbers from allocation outputs
# ---------------------------------------------------------------------------

def _allocation_numbers() -> dict:
    out = EXPLORATORY / "allocation" / "outputs"
    nums: dict = {}

    pm = _read_csv_safe(out / "part_mean_energy.csv")
    if pm is not None:
        for _, row in pm.iterrows():
            p = row.get("part", "")
            nums[f"{p}_mean_energy_wh"] = row.get("mean_energy_wh")
            nums[f"{p}_n_runs"] = row.get("n_runs")

        body_wh = pm.loc[pm["part"] == "body", "mean_energy_wh"]
        lid_wh  = pm.loc[pm["part"] == "lid",  "mean_energy_wh"]
        if not body_wh.empty and not lid_wh.empty:
            nums["lid_body_ratio"] = float(lid_wh.values[0]) / float(body_wh.values[0])

    rd = _read_csv_safe(out / "allocation_rule_errors.csv")
    if rd is not None:
        for _, row in rd.iterrows():
            p = row.get("part", "")
            nums[f"{p}_time_error_pct"] = row.get("time_error_pct")
            if "mass_error_pct" in row:
                nums[f"{p}_mass_error_pct"] = row.get("mass_error_pct")

    sec = _read_csv_safe(out / "specific_energy_per_part.csv")
    if sec is not None:
        for _, row in sec.iterrows():
            p = row.get("part", "")
            nums[f"{p}_sec_kwh_per_kg"] = row.get("sec_kwh_per_kg")

    return nums


# ---------------------------------------------------------------------------
# Scan FINDINGS files for disagreements
# ---------------------------------------------------------------------------

def _collect_disagreements() -> list[str]:
    disagreements = []
    for findings_path in EXPLORATORY.rglob("FINDINGS.md"):
        text = findings_path.read_text()
        for line in text.splitlines():
            if "DISAGREE" in line.upper() or "disagreed" in line.lower():
                project = findings_path.parent.name
                disagreements.append(f"  [{project}] {line.strip()}")
    return disagreements


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _fmt(val, fmt=".1f", fallback="[verify]") -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return fallback
    try:
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return str(val)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("Building EXPLORATORY/_summary.md ...")

    lad = _ladder_numbers()
    alc = _allocation_numbers()
    disagreements = _collect_disagreements()

    # Project status
    statuses = {
        "estimation_ladder": _project_status("estimation_ladder"),
        "allocation":        _project_status("allocation"),
        "wear_runorder":     _project_status("wear_runorder"),
    }
    exploration_notes = [
        p.stem for p in (EXPLORATORY / "explorations").glob("*.md")
        if not p.stem.endswith("_FINDINGS")
    ] if (EXPLORATORY / "explorations").exists() else []
    exploration_findings = [
        p.stem for p in (EXPLORATORY / "explorations").glob("*_FINDINGS.md")
    ] if (EXPLORATORY / "explorations").exists() else []

    # ----------------------------------------------------------------
    # Key-numbers table
    # ----------------------------------------------------------------
    # u_cnc * 13400 W rated gives approximate avg power
    u_cnc_val = lad.get("u_cnc")
    avg_pwr_str = _fmt(u_cnc_val * 13400.0 if u_cnc_val else None, ".0f")

    key_numbers_rows = [
        ("CNC avg power (W, derived)",  avg_pwr_str,
                                         "~1376 quoted (u*13400)"),
        ("CNC utilization u",            _fmt(lad.get("u_cnc"), ".3f"),
                                         "~0.10 quoted"),
        ("FDM utilization u",            _fmt(lad.get("u_fdm"), ".2f"),
                                         "~0.90 quoted"),
        ("Body mean energy (Wh)",        _fmt(alc.get("body_mean_energy_wh"), ".1f"),
                                         "~859 context doc"),
        ("Lid mean energy (Wh)",         _fmt(alc.get("lid_mean_energy_wh"), ".1f"),
                                         "~582 context doc"),
        ("Lid / body energy ratio",      _fmt(alc.get("lid_body_ratio"), ".3f"),
                                         "0.677 quoted"),
        ("L0 body error (%)",            _fmt(lad.get("body_L0_error_pct"), ".1f"),
                                         "large positive expected"),
        ("L1 body error (%)",            _fmt(lad.get("body_L1_error_pct"), ".1f"),
                                         "near 0% expected"),
        ("L2 body error (%)",            _fmt(lad.get("body_L2_error_pct"), ".1f"),
                                         "depends on SEC value"),
        ("SW near-normal ops",           _fmt(lad.get("n_near_normal"), ".0f"),
                                         "40 of 45 quoted"),
        ("Max program CV (%)",           _fmt(lad.get("max_cv_pct"), ".1f"),
                                         "[verify]"),
        ("Body SEC (kWh/kg removed)",    _fmt(alc.get("body_sec_kwh_per_kg"), ".3f"),
                                         "~0.36 context doc"),
        ("Lid SEC (kWh/kg removed)",     _fmt(alc.get("lid_sec_kwh_per_kg"), ".3f"),
                                         "~0.78 context doc"),
    ]

    num_lines = ["| Quantity | Computed | Expected / Quoted |",
                 "|---|---|---|"]
    for qty, computed, expected in key_numbers_rows:
        num_lines.append(f"| {qty} | {computed} | {expected} |")
    numbers_table = "\n".join(num_lines)

    # ----------------------------------------------------------------
    # Uncertainty table (from E3)
    # ----------------------------------------------------------------
    pv = lad.get("prog_var_df")
    if pv is not None and not pv.empty:
        pv_lines = ["| Part | Program | n | CV (%) | 95% CI (%) |",
                    "|---|---|---|---|---|"]
        for _, row in pv.iterrows():
            pv_lines.append(
                f"| {row['part']} | {row['program']} | {int(row['n_runs'])} | "
                f"{row['cv_pct']:.1f} | {row['ci_95_pct']:.1f} |"
            )
        e3_table = "\n".join(pv_lines)
    else:
        e3_table = "_Not yet computed -- run estimation_ladder first._"

    # ----------------------------------------------------------------
    # Project status table
    # ----------------------------------------------------------------
    status_symbol = {"built": "[built]", "parked": "[--]",
                     "missing": "[??]", "explored": "[desk]"}
    stat_lines = ["| Project | Status | Notes |", "|---|---|---|"]
    for name, status in statuses.items():
        sym = status_symbol.get(status, "[??]")
        notes = ""
        if status == "missing":
            notes = "run.py not yet executed"
        elif status == "parked":
            notes = "data unavailable; see _data_gaps.md"
        elif status == "built":
            findings = EXPLORATORY / name / "FINDINGS.md"
            notes = "FINDINGS.md written" if findings.exists() else "outputs present"
        stat_lines.append(f"| {name} | {sym} | {notes} |")

    for note in exploration_notes:
        stat_lines.append(f"| explorations/{note} | [desk] | desk note only |")
    for note in exploration_findings:
        stat_lines.append(f"| explorations/{note} | [explored] | FINDINGS written |")

    status_table = "\n".join(stat_lines)

    # ----------------------------------------------------------------
    # Disagreements section
    # ----------------------------------------------------------------
    if disagreements:
        disagree_section = (
            "## Discrepancies found vs quoted numbers\n\n"
            "The following disagreements were flagged by cross-checks:\n\n"
            + "\n".join(disagreements)
            + "\n\n"
        )
    else:
        disagree_section = (
            "## Discrepancies found vs quoted numbers\n\n"
            "No disagreements flagged yet. "
            "Run estimation_ladder and allocation with real data to populate this section.\n\n"
        )

    # ----------------------------------------------------------------
    # Write _summary.md
    # ----------------------------------------------------------------
    summary_text = (
        "# EXPLORATORY: analysis summary\n\n"
        f"**Generated:** {pd.Timestamp.today().strftime('%Y-%m-%d %H:%M')}\n"
        "**Source:** `python EXPLORATORY/build_summary.py`\n\n"
        "---\n\n"
        "## Key numbers computed vs quoted\n\n"
        "Rows showing `[verify]` have not yet been computed (project parked or not run).\n\n"
        f"{numbers_table}\n\n"
        "---\n\n"
        "## E3 Program-level uncertainty (95% CI on the mean)\n\n"
        f"{e3_table}\n\n"
        "---\n\n"
        f"{disagree_section}"
        "---\n\n"
        "## Project status\n\n"
        f"{status_table}\n\n"
        "---\n\n"
        "## Direction ranking (which had substance?)\n\n"
        "| Direction | Verdict | One-line finding |\n"
        "|---|---|---|\n"
        "| A1 Utilization landscape | desk | CNC u~0.10 matches literature; FDM u~0.90; meaningful gap |\n"
        "| B1 Break-even analysis | explored | 'Materials dominate' conditional on Al source; see B1_FINDINGS.md |\n"
        "| E3 Uncertainty intervals | built | See table above and uncertainty_intervals.csv |\n"
        "| C1 Specific energy | built | Per-part kWh/kg; see specific_energy_per_part.csv |\n"
        "| Wear / run order | parked | Needs CNC data |\n\n"
        "---\n\n"
        "_This file is auto-generated. Edit build_summary.py, not this file._\n"
    )

    out_path = EXPLORATORY / "_summary.md"
    out_path.write_text(summary_text)
    print(f"Written: {out_path}")

    # Print a quick diagnostic
    built = [n for n, s in statuses.items() if s == "built"]
    parked = [n for n, s in statuses.items() if s in ("parked", "missing")]
    print(f"  Projects built:  {built or 'none yet'}")
    print(f"  Projects parked: {parked or 'none'}")
    if disagreements:
        print(f"  Disagreements flagged: {len(disagreements)}")
    else:
        print("  No disagreements flagged (run with real data to populate)")


if __name__ == "__main__":
    main()
