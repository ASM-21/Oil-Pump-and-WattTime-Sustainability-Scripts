"""
ESTIMATION LADDER -- how wrong are simplified energy estimates vs measured?

Compares five estimation levels against operation-level measured ground truth:
  L0  Rated nameplate power x measured cycle time  (rated 13.4 kW CNC, 221 W FDM)
  L1  Characterized average power x measured cycle time  (verify ~1376 W CNC)
  L2  Published specific energy (SEC) x mass removed  (Kara & Li 2011 aluminum)
  L3  Program-level total measured energy (sum of all operations; no UUID needed)
  L4  Operation-level UUID attribution (ground truth)

Key outputs:
  - Signed % error per level, per part/program (table + bar chart)
  - CNC and FDM utilization factors (u = mean_power / rated_power)
  - Replication requirements table n = (1.96 * CV / r)^2 per operation category

Run from repo root:
    python EXPLORATORY/estimation_ladder/run.py

Set CNC_DATA_DIR first -- see EXPLORATORY/shared/adapters.py header for instructions.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared.style import apply_style, save_fig, COLORS, MARKERS
from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared import adapters

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

# ---------------------------------------------------------------------------
# Machine parameters -- VERIFY THESE BEFORE CITING IN THE PAPER
# ---------------------------------------------------------------------------
# CNC: Hurco VMX30Ui, 18 hp spindle = 13.4 kW at 12,000 rpm.
# NOTE: total connected load (including hydraulics, way lube, chip conveyor)
# is LARGER than this and is readable from the machine's electrical plate.
# Report both variants if you can photograph the plate; parameterize here.
CNC_RATED_POWER_W = 13_400.0  # spindle rating only -- update if you have the plate value

# FDM: Ultimaker 2+ Extended
FDM_RATED_POWER_W = 221.0     # nameplate
FDM_MEASURED_POWER_W = 200.0  # approximate measured draw; update from your AM CSV

# ---------------------------------------------------------------------------
# Mass removed -- single source of truth is EXPLORATORY/bom.csv
# ---------------------------------------------------------------------------
# Owner-verified masses live in bom.csv (body 1880/443/1437 g, lid 518/70/448 g,
# 2026-07-09). mass_removed = stock_mass - finished_mass; removed-mass basis is
# the paper's single stated basis. The fallback constants match bom.csv and
# exist only so this script stays runnable if bom.csv moves.
def _mass_removed_g() -> tuple[dict[str, float], bool]:
    fallback = {"body": 1437.0, "lid": 448.0}
    try:
        bom = adapters.load_bom().set_index("part")
        return ({p: float(bom.loc[p, "mass_removed_g"]) for p in ("body", "lid")},
                True)
    except Exception:
        return fallback, False

MASS_REMOVED_G, MASS_DATA_VERIFIED = _mass_removed_g()

# ---------------------------------------------------------------------------
# Specific Energy Consumption (SEC) from literature (L2 estimator)
# ---------------------------------------------------------------------------
# Kara & Li (2011), aluminum milling, kWh/kg.
# The range for aluminum is roughly 1.5 to 4.0 kWh/kg depending on conditions.
# Report which value you use and where it comes from.
SEC_KARA_LI_KWH_PER_KG = 2.5   # representative midpoint; verify against paper


def load() -> pd.DataFrame:
    try:
        return adapters.load_operation_energy()
    except (adapters.DataNotInRepo, NotImplementedError) as e:
        _gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
        with _gap.open("a") as f:
            f.write(f"\n## estimation_ladder (parked)\n- {e}\n")
        print(f"PARKED: {e}")
        sys.exit(0)


def compute(df: pd.DataFrame) -> dict:
    result: dict = {}

    # ------------------------------------------------------------------
    # Fleet average power -- verified two independent ways
    # ------------------------------------------------------------------
    # Path A: total energy / total duration (energy-weighted mean power)
    total_wh = df["energy_wh"].sum()
    total_s = df["duration_s"].sum()
    avg_power_a = total_wh * 3600.0 / total_s

    # Path B: origin-forced least-squares regression slope (J on s)
    x = df["duration_s"].to_numpy()
    y = (df["energy_wh"] * 3600.0).to_numpy()
    avg_power_b = float(x @ y / (x @ x))

    log.cross_check("CNC fleet avg power (W)", avg_power_a, avg_power_b,
                    note="Path A=energy/duration, Path B=OLS slope through origin")
    log.check_against_expected("CNC fleet avg power (W)", avg_power_a, 1376.0,
                               note="quoted in paper; recomputed here")
    result["avg_power_w"] = avg_power_a

    # ------------------------------------------------------------------
    # Utilization factors
    # ------------------------------------------------------------------
    u_cnc = avg_power_a / CNC_RATED_POWER_W
    u_fdm = FDM_MEASURED_POWER_W / FDM_RATED_POWER_W
    log.check_against_expected("CNC utilization factor u", u_cnc, 0.10, rel_tol=0.30,
                               note="expected ~0.10; 30% tol because rated-power basis unclear")
    result["u_cnc"] = u_cnc
    result["u_fdm"] = u_fdm

    # ------------------------------------------------------------------
    # Per-program, per-run energy (L4 ground truth = L3 for our data)
    # ------------------------------------------------------------------
    # L3 = program-level measured total (what you'd get from a program-level meter)
    # L4 = same total, but with operation attribution  -> numerically equal here
    program_runs = (
        df.groupby(["part", "program", "run_id"])
        .agg(
            L4_energy_wh=("energy_wh", "sum"),
            total_duration_s=("duration_s", "sum"),
        )
        .reset_index()
    )
    program_runs["L3_energy_wh"] = program_runs["L4_energy_wh"]

    # L0: rated power x measured duration
    program_runs["L0_energy_wh"] = CNC_RATED_POWER_W * program_runs["total_duration_s"] / 3600.0

    # L1: characterized average power x measured duration
    program_runs["L1_energy_wh"] = avg_power_a * program_runs["total_duration_s"] / 3600.0

    # L2: SEC x mass removed -- one value per part type, not per run
    mass_kwh = {
        part: SEC_KARA_LI_KWH_PER_KG * grams / 1000.0  # -> kWh
        for part, grams in MASS_REMOVED_G.items()
    }
    program_runs["L2_energy_wh"] = program_runs["part"].map(mass_kwh) * 1000.0  # Wh

    # Signed % error: (estimate - ground_truth) / ground_truth * 100
    for lvl in ["L0", "L1", "L2", "L3"]:
        program_runs[f"{lvl}_error_pct"] = (
            (program_runs[f"{lvl}_energy_wh"] - program_runs["L4_energy_wh"])
            / program_runs["L4_energy_wh"] * 100.0
        )

    result["program_runs"] = program_runs

    # ------------------------------------------------------------------
    # Dual-path check on L0 aggregate error
    # ------------------------------------------------------------------
    total_L0 = program_runs["L0_energy_wh"].sum()
    total_L4 = program_runs["L4_energy_wh"].sum()
    l0_err_agg = (total_L0 - total_L4) / total_L4 * 100.0
    l0_err_mean_of_runs = program_runs["L0_error_pct"].mean()
    log.cross_check("L0 aggregate error (agg vs mean-of-runs)",
                    l0_err_agg, l0_err_mean_of_runs, rel_tol=0.10,
                    note="should agree if program energies are similar across runs")

    # ------------------------------------------------------------------
    # Per-operation CV stats -> replication table
    # ------------------------------------------------------------------
    op_stats = (
        df.groupby(["part", "operation_id", "operation_cat"])
        .agg(
            mean_wh=("energy_wh", "mean"),
            std_wh=("energy_wh", "std"),
            n_runs=("energy_wh", "count"),
        )
        .reset_index()
    )
    op_stats = op_stats[op_stats["n_runs"] >= 3].copy()
    op_stats["cv_pct"] = (op_stats["std_wh"] / op_stats["mean_wh"] * 100.0).round(1)
    # n = (1.96 * CV / r)^2  where r is relative margin
    for r, label in [(0.05, "n_r5pct"), (0.10, "n_r10pct")]:
        op_stats[label] = np.ceil((1.96 * op_stats["cv_pct"] / 100.0 / r) ** 2).astype(int)

    result["op_stats"] = op_stats

    # ------------------------------------------------------------------
    # Normality check (Shapiro-Wilk) -- verifies the "40 of 45" quoted number
    # ------------------------------------------------------------------
    from scipy import stats as scipy_stats  # noqa: PLC0415
    norm_rows = []
    for (part, op_id), grp in df.groupby(["part", "operation_id"]):
        n = len(grp)
        if n < 4:  # Shapiro-Wilk needs at least 4 samples
            continue
        stat, p = scipy_stats.shapiro(grp["energy_wh"].values)
        norm_rows.append({"part": part, "operation_id": op_id,
                          "n_runs": n, "sw_stat": round(stat, 4),
                          "p_value": round(p, 4), "near_normal": p > 0.05})
    norm_df = pd.DataFrame(norm_rows)
    n_normal = int(norm_df["near_normal"].sum()) if not norm_df.empty else 0
    n_tested = len(norm_df)
    log.check_against_expected(
        "operations near-normal (SW p>0.05)",
        float(n_normal), 40.0, rel_tol=0.15,
        note="quoted '40 of 45' in paper; computed here on (part, operation_id) groups"
    )
    result["norm_df"] = norm_df
    result["n_normal"] = n_normal
    result["n_tested"] = n_tested

    # ------------------------------------------------------------------
    # E3: Program-level uncertainty intervals from repeated runs
    # ------------------------------------------------------------------
    prog_var = (
        program_runs.groupby(["part", "program"])
        .agg(
            mean_wh=("L4_energy_wh", "mean"),
            std_wh=("L4_energy_wh", "std"),
            n_runs=("L4_energy_wh", "count"),
        )
        .reset_index()
    )
    prog_var = prog_var[prog_var["n_runs"] >= 3].copy()
    prog_var["cv_pct"] = (prog_var["std_wh"] / prog_var["mean_wh"] * 100).round(1)
    # 95% CI on the mean: 1.96 * (std / sqrt(n))
    prog_var["ci_95_wh"] = (
        1.96 * prog_var["std_wh"] / np.sqrt(prog_var["n_runs"])
    ).round(3)
    prog_var["ci_95_pct"] = (prog_var["ci_95_wh"] / prog_var["mean_wh"] * 100).round(1)
    result["prog_var"] = prog_var

    result["df"] = df
    return result


def smoke_test(r: dict) -> None:
    df = r["df"]
    pr = r["program_runs"]

    require(len(df) > 0, "energy table is empty -- nothing to analyze")
    require((df["energy_wh"] > 0).all(), "non-positive energy_wh values in table")
    # Homing (TRANSITION_OVERHEAD) rows are synthesized with Duration_Sec=0
    # by EnergyForFeatureLib; they carry energy but no attributable time.
    require((df["duration_s"] >= 0).all(), "negative duration_s values in table")
    require((df.loc[df["operation_cat"] != "homing", "duration_s"] > 0).all(),
            "non-positive duration_s outside homing rows")
    require((pr["L4_energy_wh"] > 0).all(), "non-positive L4 ground truth per run")
    require(
        (pr["L0_energy_wh"] > pr["L4_energy_wh"]).all(),
        "L0 (rated power x time) must always EXCEED measured energy for a machining center. "
        "If this fails, check CNC_RATED_POWER_W or the measured data."
    )
    require(
        0.03 < r["u_cnc"] < 0.40,
        f"CNC utilization factor {r['u_cnc']:.3f} is outside the plausible range 0.03-0.40. "
        "Check CNC_RATED_POWER_W and measured average power."
    )
    require(
        0.70 < r["u_fdm"] < 1.10,
        f"FDM utilization factor {r['u_fdm']:.3f} is outside the expected range 0.70-1.10. "
        "Check FDM_RATED_POWER_W and FDM_MEASURED_POWER_W."
    )
    require(r["n_tested"] > 0,
            "Shapiro-Wilk test produced no results -- need at least 4 runs per operation")
    # FIXTURE_SMOKE=1 (set only by EXPLORATORY/smoke_fixture_all.py) runs this
    # project on synthetic fixtures, where checks against numbers quoted from
    # the MEASURED campaign are expected to disagree. Structural invariants
    # above still apply; only the quoted-number gate is downgraded to a warning.
    if os.environ.get("FIXTURE_SMOKE") == "1":
        if log.any_disagreements():
            print("FIXTURE_SMOKE: quoted-number cross-checks disagreed on "
                  "synthetic data (expected); see FINDINGS for the table")
    else:
        require(not log.any_disagreements(),
                "a cross-check DISAGREED -- investigate before reporting results")


def plot(r: dict) -> None:
    import matplotlib.pyplot as plt
    apply_style()

    pr = r["program_runs"]
    levels = ["L0", "L1", "L2", "L3"]
    labels = ["L0 rated", "L1 avg pwr", "L2 SEC", "L3 prog total"]

    # ---- Bar chart: mean signed % error per estimation level, by part ----
    fig, ax = plt.subplots()
    x = np.arange(len(levels))
    width = 0.35

    for i, part in enumerate(["body", "lid"]):
        part_data = pr[pr["part"] == part]
        if part_data.empty:
            continue
        means = [part_data[f"{lvl}_error_pct"].mean() for lvl in levels]
        bars = ax.bar(x + i * width - width / 2, means, width,
                      label=part.capitalize(), color=COLORS[i], alpha=0.85)

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right")
    ax.set_ylabel("Signed error (%)\n(estimate - measured) / measured")
    ax.set_title("Estimation error by level")
    ax.legend()
    save_fig(fig, str(OUT / "estimation_error_by_level"))

    # ---- Duration vs energy scatter with L0 and L1 slope lines ----
    df = r["df"]
    fig2, ax2 = plt.subplots()
    ax2.scatter(df["duration_s"] / 60, df["energy_wh"],
                s=6, alpha=0.5, color=COLORS[0], label="Operations (L4)")
    t_range = np.linspace(0, df["duration_s"].max(), 100)
    ax2.plot(t_range / 60, r["avg_power_w"] * t_range / 3600,
             color=COLORS[1], linestyle="--", label=f"L1 ({r['avg_power_w']:.0f} W avg)")
    ax2.plot(t_range / 60, CNC_RATED_POWER_W * t_range / 3600,
             color=COLORS[2], linestyle=":", label=f"L0 ({CNC_RATED_POWER_W/1000:.1f} kW rated)")
    ax2.set_xlabel("Duration (min)")
    ax2.set_ylabel("Energy (Wh)")
    ax2.set_title("Duration vs energy with estimation slopes")
    ax2.legend()
    save_fig(fig2, str(OUT / "duration_vs_energy_slopes"))


def write_findings(r: dict) -> None:
    pr = r["program_runs"]
    op = r["op_stats"]

    # Save tables
    pr.to_csv(OUT / "program_run_errors.csv", index=False)
    op.to_csv(OUT / "operation_cv_replication.csv", index=False)
    if "norm_df" in r and not r["norm_df"].empty:
        r["norm_df"].to_csv(OUT / "normality_shapiro_wilk.csv", index=False)
    if "prog_var" in r and not r["prog_var"].empty:
        r["prog_var"].to_csv(OUT / "uncertainty_intervals.csv", index=False)

    # Summary by part and level
    summary_rows = []
    for part in ["body", "lid"]:
        part_runs = pr[pr["part"] == part]
        if part_runs.empty:
            continue
        row: dict = {"part": part, "n_runs": len(part_runs),
                     "L4_mean_wh": part_runs["L4_energy_wh"].mean(),
                     "u_cnc": r["u_cnc"], "u_fdm": r["u_fdm"]}
        for lvl in ["L0", "L1", "L2", "L3"]:
            row[f"{lvl}_mean_error_pct"] = part_runs[f"{lvl}_error_pct"].mean()
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_csv(OUT / "summary_by_part.csv", index=False)

    # Build the per-part error table string outside the f-string (avoids backslash-in-fstring)
    table_lines = ["| Part | n_runs | L0 rated | L1 avg pwr | L2 SEC | L3 prog total |",
                   "|---|---|---|---|---|---|"]
    for row in summary_rows:
        table_lines.append(
            f"| {row['part']} | {int(row['n_runs'])} | "
            f"{row['L0_mean_error_pct']:.1f}% | {row['L1_mean_error_pct']:.1f}% | "
            f"{row['L2_mean_error_pct']:.1f}% | {row['L3_mean_error_pct']:.1f}% |"
        )
    error_table = "\n".join(table_lines)

    verified_note = ("\nMasses read from EXPLORATORY/bom.csv (owner-verified 2026-07-09), "
                     "removed-mass basis." if MASS_DATA_VERIFIED else
                     "\nNOTE: bom.csv was not readable; MASS_REMOVED_G fell back to "
                     "context-doc constants. L2 errors are approximate until confirmed.")

    avg_w = r["avg_power_w"]
    u_cnc = r["u_cnc"]
    u_fdm = r["u_fdm"]
    l0_mean_err = pr["L0_error_pct"].mean()
    l1_mean_err = pr["L1_error_pct"].mean()
    n_runs = len(pr)
    body_g = MASS_REMOVED_G["body"]
    lid_g = MASS_REMOVED_G["lid"]

    # Build E3 uncertainty table outside f-string
    pv = r.get("prog_var")
    if pv is not None and not pv.empty:
        pv_lines = ["| Part | Program | n_runs | Mean (Wh) | CV (%) | 95% CI (Wh) | 95% CI (%) |",
                    "|---|---|---|---|---|---|---|"]
        for _, row in pv.iterrows():
            pv_lines.append(
                f"| {row['part']} | {row['program']} | {int(row['n_runs'])} | "
                f"{row['mean_wh']:.1f} | {row['cv_pct']:.1f} | "
                f"{row['ci_95_wh']:.1f} | {row['ci_95_pct']:.1f} |"
            )
        e3_section = (
            "### E3 Program-level uncertainty (95% CI on the mean from repeated runs)\n"
            + "\n".join(pv_lines)
            + "\n- Full table: outputs/uncertainty_intervals.csv\n\n"
        )
    else:
        e3_section = (
            "### E3 Program-level uncertainty\n"
            "- Skipped: fewer than 3 runs per program after filtering.\n\n"
        )

    findings_text = (
        "# estimation_ladder: findings\n\n"
        f"**Status:** explored\n"
        f"**Date:** {pd.Timestamp.today().date()}\n\n"
        "## Headline\n"
        f"Rated-power (L0) estimation overestimates CNC machining energy by approximately\n"
        f"{l0_mean_err:.0f}% on average (n={n_runs} program runs), consistent with the\n"
        f"CNC utilization factor u = {u_cnc:.3f} (mean {avg_w:.0f} W / rated "
        f"{CNC_RATED_POWER_W:.0f} W). The characterized-average-power estimator (L1)\n"
        f"reduces error to approximately {l1_mean_err:.0f}% at program level.\n"
        f"FDM utilization factor u = {u_fdm:.2f}, making L0 nearly correct for FDM.\n\n"
        "## Numbers\n\n"
        "### Per-part estimation error (mean signed %, averaged over all runs)\n"
        f"{error_table}\n\n"
        "### Utilization factors\n"
        f"- CNC (Hurco VMX30Ui): u = {u_cnc:.3f} (mean {avg_w:.1f} W / {CNC_RATED_POWER_W:.0f} W rated)\n"
        f"- FDM (Ultimaker 2+Ext): u = {u_fdm:.2f} ({FDM_MEASURED_POWER_W:.0f} W measured / {FDM_RATED_POWER_W:.0f} W rated)\n"
        f"{verified_note}\n\n"
        "## Verification\n\n"
        f"{log.to_markdown()}\n"
        "## Caveats\n"
        "- Rated power basis for CNC is spindle rating (18 hp / 13.4 kW). Total connected\n"
        "  load is higher and readable from the machine electrical plate. This choice changes\n"
        "  the utilization factor and L0 error; report both variants if the plate is available.\n"
        f"- L2 (SEC) uses Kara and Li (2011) midpoint value ({SEC_KARA_LI_KWH_PER_KG} kWh/kg). "
        "The range for aluminum milling is 1.5 to 4.0 kWh/kg. Report which value is used.\n"
        f"- Mass removed values (body {body_g:.0f} g, lid {lid_g:.0f} g) are from context doc "
        "estimates, not yet verified against measured stock/finished masses.\n"
        "- FDM utilization factor is computed from spec-sheet values (200 W / 221 W rated),\n"
        "  not from AM CSV data. Wire load_am_energy() in the adapter for a full comparison.\n"
        "- Single machine, single material (Al 6061), single facility (IN-MaC).\n\n"
        "## Feeds the journal paper?\n"
        "Yes -- Tier A, highest priority. Supplies:\n"
        "- Table: signed % error per level per part (new Results subsection 4.3)\n"
        "- u_cnc and u_fdm for the utilization factor paragraph (Discussion)\n"
        "- Replication table n=(1.96*CV/r)^2 per operation category (Results 4.2)\n"
        f"- Regression slope (L1 basis) = {avg_w:.0f} W, verified two ways\n\n"
        "### Normality (Shapiro-Wilk, p > 0.05 = near-normal)\n"
        f"- Operations tested (>= 4 runs): {r['n_tested']}\n"
        f"- Near-normal: {r['n_normal']} of {r['n_tested']} (paper quotes 40 of 45)\n"
        "- Full per-operation results: outputs/normality_shapiro_wilk.csv\n\n"
        f"{e3_section}"
        "## How to extend\n"
        "- Wire FDM data (AM_DATA_DIR) for a proper CNC vs FDM comparison figure.\n"
        "- Replace spindle rating with total connected load if the electrical plate is photographed.\n"
        "- Verify mass_removed values and set MASS_DATA_VERIFIED=True to remove the L2 caveat.\n"
    )
    (Path(__file__).parent / "FINDINGS.md").write_text(findings_text)
    print(f"FINDINGS.md written to {Path(__file__).parent / 'FINDINGS.md'}")


def main() -> None:
    df = load()
    r = compute(df)
    try:
        smoke_test(r)
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
    plot(r)
    write_findings(r)
    print("OK")


if __name__ == "__main__":
    main()
