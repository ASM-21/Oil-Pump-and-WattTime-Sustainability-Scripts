"""
UNCERTAINTY + DESIGN-STAGE PREDICTION -- the interval reviewers will ask
for, and the CAM-time model that connects measurement back to design.

Two halves:

  A. Product-footprint uncertainty. Per-operation replicate statistics are
     propagated (Monte Carlo, cross-checked against the exact delta method)
     into a confidence interval on total manufacturing energy, then combined
     with bom.csv masses under aluminum-carbon and grid-intensity scenarios
     into footprint intervals and manufacturing-share intervals.

  B. Design-stage prediction. A duration-by-category model (per-category
     mean power, i.e. the power-decomposition lambda table in regression
     form) predicts program energy from CAM-planned durations,
     leave-one-program-out. If it predicts well, energy footprints are
     estimable at CAM time, before a single chip is cut; that is the JMD
     design-stage hook.

Always runs on fixtures (known truth, real pipeline); adds measured tables
when CNC_DATA_DIR points at the real Al6061 folder.

Run from the repo root:
    python EXPLORATORY/uncertainty_prediction/run.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from EXPLORATORY.shared.checks import CheckLog, require, SmokeTestFailure
from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared import fixtures, montecarlo

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

# Scenario axes (kept identical to explorations/B1_breakeven.py so the two
# analyses can be read together).
CF_SCENARIOS = {
    "Virgin (global avg)":         12.0,
    "Virgin (low-carbon smelter)":  4.0,
    "50% recycled mix":             6.5,
    "Recycled (secondary)":         0.5,
}
GRID_CI_KG_PER_KWH = 0.40   # representative US grid; sweep in B1, fixed here
MASS_SD_G = 5.0             # weighing repeatability assumption; state in paper


# ---------------------------------------------------------------------------
# A. Footprint uncertainty
# ---------------------------------------------------------------------------

def footprint_uncertainty(df: pd.DataFrame, tag: str) -> list[str]:
    from EXPLORATORY.shared import adapters

    bom = adapters.load_bom().set_index("part")
    lines = [f"### Footprint uncertainty ({tag})", ""]
    rows = []

    for part, g in df.groupby("part"):
        stats = montecarlo.fit_operation_stats(g)
        samples = montecarlo.mc_total_energy(stats, n_draws=20000, seed=1)
        d_mean, d_sd = montecarlo.delta_total_energy(stats)
        log.cross_check(f"{tag}/{part} total energy MC vs delta (mean, Wh)",
                        float(samples.mean()), d_mean, rel_tol=0.01)
        log.cross_check(f"{tag}/{part} total energy MC vs delta (sd, Wh)",
                        float(samples.std(ddof=1)), d_sd, rel_tol=0.10)
        e = montecarlo.summarize_samples(samples)
        ci_half_pct = 100 * (e["p97.5"] - e["p2.5"]) / 2 / e["mean"]
        lines.append(f"- {part}: mean {e['mean']:.0f} Wh, "
                     f"95% CI +/-{ci_half_pct:.1f}%")

        for scen, cf in CF_SCENARIOS.items():
            fp = montecarlo.footprint_from_energy(
                samples,
                mass_g=float(bom.loc[part, "stock_mass_g"]),
                mass_sd_g=MASS_SD_G,
                cf_al_kg_per_kg=cf,
                grid_ci_kg_per_kwh=GRID_CI_KG_PER_KWH,
            )
            s_total = montecarlo.summarize_samples(fp["total_kg"])
            s_share = montecarlo.summarize_samples(fp["mfg_share_pct"])
            rows.append({
                "tag": tag, "part": part, "scenario": scen,
                "cf_al": cf, "grid_ci": GRID_CI_KG_PER_KWH,
                "total_kgco2e_mean": s_total["mean"],
                "total_kgco2e_p2.5": s_total["p2.5"],
                "total_kgco2e_p97.5": s_total["p97.5"],
                "mfg_share_pct_mean": s_share["mean"],
                "mfg_share_pct_p2.5": s_share["p2.5"],
                "mfg_share_pct_p97.5": s_share["p97.5"],
            })

    table = pd.DataFrame(rows)
    table.to_csv(OUT / f"footprint_intervals_{tag}.csv", index=False)
    figure_intervals(table, tag)
    lines.append("")
    return lines


def figure_intervals(table: pd.DataFrame, tag: str) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.5, 2.6))
    body = table[table["part"] == "body"]
    y = np.arange(len(body))
    ax.errorbar(
        body["mfg_share_pct_mean"], y,
        xerr=[body["mfg_share_pct_mean"] - body["mfg_share_pct_p2.5"],
              body["mfg_share_pct_p97.5"] - body["mfg_share_pct_mean"]],
        fmt="o", color=COLORS[0], capsize=2, markersize=3)
    ax.set_yticks(y, body["scenario"], fontsize=6)
    ax.set_xlabel("Manufacturing share of body footprint (%), 95% interval")
    ax.set_title(f"grid CI = {GRID_CI_KG_PER_KWH} kgCO2e/kWh ({tag})", fontsize=7)
    save_fig(fig, str(OUT / f"mfg_share_intervals_{tag}"))


# ---------------------------------------------------------------------------
# B. Design-stage prediction (leave-one-program-out)
# ---------------------------------------------------------------------------

def design_stage_prediction(df: pd.DataFrame, tag: str) -> list[str]:
    work = df[~df["operation_cat"].isin(["idle", "homing"])].copy()
    programs = sorted(work["program"].unique())
    rows = []

    for held_out in programs:
        train = work[work["program"] != held_out]
        test = work[work["program"] == held_out]
        if train.empty or test.empty:
            continue
        # Per-category mean power from training programs (through-origin
        # slope of energy on duration = duration-weighted mean power).
        slopes = (train.groupby("operation_cat")
                  .apply(lambda g: g["energy_wh"].sum() * 3600.0
                         / g["duration_s"].sum(), include_groups=False))
        fallback = train["energy_wh"].sum() * 3600.0 / train["duration_s"].sum()

        for run_id, tg in test.groupby("run_id"):
            pred_wh = float(sum(
                slopes.get(cat, fallback) * dur / 3600.0
                for cat, dur in zip(tg["operation_cat"], tg["duration_s"])
            ))
            true_wh = float(tg["energy_wh"].sum())
            rows.append({
                "tag": tag, "held_out_program": held_out, "run_id": run_id,
                "pred_wh": pred_wh, "true_wh": true_wh,
                "err_pct": 100 * (pred_wh - true_wh) / true_wh,
            })

    table = pd.DataFrame(rows)
    table.to_csv(OUT / f"design_stage_loo_{tag}.csv", index=False)
    figure_prediction(table, tag)

    mae = table["err_pct"].abs().mean()
    lines = [
        f"### Design-stage prediction ({tag})",
        "",
        f"- Leave-one-program-out over {table['held_out_program'].nunique()} "
        f"programs, {len(table)} program-runs",
        f"- Mean |error| {mae:.1f}%, worst {table['err_pct'].abs().max():.1f}%",
        "",
    ]
    if tag == "fixture":
        require(mae < 60.0,
                f"fixture design-stage MAE {mae:.0f}% out of range; model broken")
    return lines


def figure_prediction(table: pd.DataFrame, tag: str) -> None:
    import matplotlib.pyplot as plt

    apply_style()
    fig, ax = plt.subplots(figsize=(3.0, 3.0))
    ax.scatter(table["true_wh"], table["pred_wh"], s=10, color=COLORS[5])
    lim = [0, max(table["true_wh"].max(), table["pred_wh"].max()) * 1.05]
    ax.plot(lim, lim, linewidth=0.8, color=COLORS[0])
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("Measured program energy (Wh)")
    ax.set_ylabel("Predicted from durations (Wh)")
    ax.set_title(f"Duration-by-category model, LOPO ({tag})", fontsize=7)
    save_fig(fig, str(OUT / f"design_stage_scatter_{tag}"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze_source(tag: str) -> list[str]:
    from EXPLORATORY.shared import adapters

    df = adapters.load_operation_energy()
    return (footprint_uncertainty(df, tag)
            + design_stage_prediction(df, tag))


def main() -> None:
    sections: list[str] = []

    saved = os.environ.get("CNC_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.generate_fixture_dataset(tmp, n_runs=3, seed=7)
            os.environ["CNC_DATA_DIR"] = tmp
            sections += analyze_source("fixture")
    finally:
        if saved is None:
            os.environ.pop("CNC_DATA_DIR", None)
        else:
            os.environ["CNC_DATA_DIR"] = saved

    real_note = ("Real CNC data not reachable in this run; set CNC_DATA_DIR "
                 "and re-run for the measured intervals (tag 'measured').")
    if os.environ.get("CNC_DATA_DIR"):
        try:
            sections += analyze_source("measured")
            real_note = "Measured tables written (tag 'measured')."
        except Exception as e:
            gap = ROOT / "EXPLORATORY" / "_data_gaps.md"
            with gap.open("a") as f:
                f.write(f"- uncertainty_prediction (real-data pass): {e}\n")
            real_note = f"Real-data pass parked: {e}"

    require(not log.any_disagreements(), "a cross-check disagreed")

    findings = Path(__file__).parent / "FINDINGS.md"
    findings.write_text(
        "# Uncertainty and design-stage prediction: findings\n\n"
        "A: replicate statistics propagated to footprint intervals "
        "(Monte Carlo, cross-checked against the exact delta method; "
        "carbon factors are scenario axes, never averaged). Intervals answer "
        "'energy of the average part'; switch use_se=False in "
        "shared/montecarlo.py for single-part prediction intervals.\n\n"
        "B: per-category duration model evaluated leave-one-program-out; "
        "small errors mean energy is predictable from CAM-planned times "
        "before machining, which is the design-stage claim.\n\n"
        + "\n".join(sections) + "\n"
        f"{real_note}\n\n"
        "## Verification\n\n" + log.to_markdown() + "\n"
    )
    print("OK uncertainty_prediction")


if __name__ == "__main__":
    try:
        main()
    except SmokeTestFailure as e:
        print(f"SMOKE TEST FAILED: {e}")
        sys.exit(1)
