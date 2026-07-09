"""
B1 BREAK-EVEN -- when does manufacturing energy stop being negligible?

The paper claims materials dominate the oil pump footprint (~98%, aluminum-heavy).
This script interrogates that claim directly: sweeps aluminum embodied carbon
intensity and grid carbon intensity, and finds the break-even where manufacturing
crosses 5% and 10% of total product footprint.

This is self-contained -- no CNC_DATA_DIR needed. It uses the total measured
energy from the context docs (update TOTAL_ENERGY_WH after running estimation_ladder).

Run from repo root:
    python EXPLORATORY/explorations/B1_breakeven.py

Key finding this produces:
  At virgin aluminum (~12 kg CO2e/kg): manufacturing < 2% of total.
  At recycled aluminum (~0.5 kg CO2e/kg): manufacturing can exceed 20%.
  -> "Materials dominate" is conditional on the aluminum source.
  -> Decarbonizing aluminum is exactly what makes this monitoring matter.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from EXPLORATORY.shared.style import apply_style, save_fig, COLORS
from EXPLORATORY.shared.checks import CheckLog

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "outputs"
OUT.mkdir(exist_ok=True)
log = CheckLog()

# ---------------------------------------------------------------------------
# Energy inputs -- UPDATE these after running estimation_ladder
# ---------------------------------------------------------------------------
# Total measured CNC machining energy per part (Wh), summed across all programs.
# Context doc estimates until estimation_ladder confirms them:
#   body total: ~4 programs x ~215 Wh/program = ~860 Wh (paper quotes 0.859 kWh CNC)
#   lid total:  0.677 * body = ~582 Wh (paper quotes 67.7% of body)
TOTAL_ENERGY_WH = {
    "body": 859.0,   # Wh -- update from estimation_ladder/outputs/summary_by_part.csv
    "lid":  582.0,   # Wh -- update from estimation_ladder/outputs/summary_by_part.csv
}
ENERGY_VERIFIED = False  # set True once estimation_ladder has run

# ---------------------------------------------------------------------------
# Mass inputs -- owner-verified values committed in EXPLORATORY/bom.csv
# ---------------------------------------------------------------------------
# Stock mass is needed for E_materials = stock_mass * CF_aluminum.
# Loaded from bom.csv (single source of truth); the fallback constants below
# match it and exist only so this script stays self-contained if bom.csv moves.
def _stock_masses() -> dict[str, float]:
    bom_path = ROOT / "EXPLORATORY" / "bom.csv"
    fallback = {"body": 1880.0, "lid": 518.0}  # owner-verified 2026-07-09
    if not bom_path.exists():
        return fallback
    masses = {}
    for line in bom_path.read_text().splitlines()[1:]:
        cells = line.split(",")
        if len(cells) >= 2 and cells[0] in fallback:
            masses[cells[0]] = float(cells[1])
    return masses or fallback

STOCK_MASS_G = _stock_masses()
MASS_VERIFIED = True  # bom.csv holds owner-verified masses (2026-07-09)

# AM parts (drive shaft) omitted here because AM energy is small and masses
# are not estimated. Add when AM data is available.


# ---------------------------------------------------------------------------
# Aluminum carbon factors from literature
# ---------------------------------------------------------------------------
# All in kg CO2e per kg of aluminum
CF_SCENARIOS = {
    "Virgin (global avg)":         12.0,   # IAI global average primary aluminum
    "Virgin (low-carbon smelter)":  4.0,   # hydropower-intensive smelting
    "50% recycled mix":             6.5,   # approximate
    "Recycled (secondary)":         0.5,   # scrap-based secondary aluminum
}

# Grid carbon intensity range for the sweep (kg CO2e / kWh)
GRID_CI_RANGE = (0.02, 0.80)   # renewable (0.02) to coal-heavy US grid (0.80)
AL_CF_RANGE   = (0.3,  17.0)   # recycled to energy-intensive primary

# Our operating grid (Indiana grid, approximate)
INDIANA_GRID_CI = 0.45  # kg CO2e/kWh (MISO region, approximate average)


def compute() -> dict:
    result: dict = {}

    # Total product footprint at each aluminum scenario and grid intensity
    total_mass_g = sum(STOCK_MASS_G.values())
    total_mass_kg = total_mass_g / 1000
    total_energy_wh = sum(TOTAL_ENERGY_WH.values())
    total_energy_kwh = total_energy_wh / 1000

    # --- Point estimates at each aluminum scenario ---
    scenario_rows = []
    for scenario_name, cf_al in CF_SCENARIOS.items():
        e_mat = total_mass_kg * cf_al               # kg CO2e from materials
        e_mfg = total_energy_kwh * INDIANA_GRID_CI  # kg CO2e from manufacturing
        total = e_mat + e_mfg
        mfg_share = e_mfg / total * 100 if total > 0 else 0
        scenario_rows.append({
            "scenario": scenario_name,
            "cf_al_kgco2e_per_kg": cf_al,
            "e_materials_kgco2e": round(e_mat, 3),
            "e_manufacturing_kgco2e": round(e_mfg, 4),
            "total_kgco2e": round(total, 3),
            "manufacturing_share_pct": round(mfg_share, 2),
        })
    result["scenario_df"] = pd.DataFrame(scenario_rows)

    # Check that our baseline (~2% manufacturing share) is in the right ballpark
    virgin_row = next(r for r in scenario_rows if "global avg" in r["scenario"].lower())
    log.check_against_expected(
        "manufacturing share at virgin aluminum + Indiana grid",
        virgin_row["manufacturing_share_pct"], 2.0, rel_tol=0.50,
        note="paper quotes ~2%; 50% tol because energy and mass values are estimates"
    )

    # --- 2D sweep: CF_al vs grid CI ---
    cf_al_vals  = np.linspace(AL_CF_RANGE[0],   AL_CF_RANGE[1],   120)
    ci_grid_vals = np.linspace(GRID_CI_RANGE[0], GRID_CI_RANGE[1], 120)
    CF_GRID, CI_GRID = np.meshgrid(cf_al_vals, ci_grid_vals)

    e_mat_grid = total_mass_kg * CF_GRID          # kg CO2e
    e_mfg_grid = total_energy_kwh * CI_GRID       # kg CO2e
    total_grid  = e_mat_grid + e_mfg_grid
    mfg_share_grid = e_mfg_grid / total_grid * 100

    result.update({
        "cf_al_vals": cf_al_vals, "ci_grid_vals": ci_grid_vals,
        "CF_GRID": CF_GRID, "CI_GRID": CI_GRID,
        "mfg_share_grid": mfg_share_grid,
        "total_mass_kg": total_mass_kg,
        "total_energy_kwh": total_energy_kwh,
    })

    # --- Break-even thresholds ---
    # At our operating grid, what CF_al makes manufacturing = threshold?
    # threshold = e_mfg / (e_mat + e_mfg)
    # => e_mat = e_mfg * (1/threshold - 1)
    # => cf_al = e_mfg * (1/threshold - 1) / total_mass_kg
    e_mfg_fixed = total_energy_kwh * INDIANA_GRID_CI
    breakeven_rows = []
    for threshold_pct in [5.0, 10.0, 20.0]:
        t = threshold_pct / 100
        cf_breakeven = e_mfg_fixed * (1/t - 1) / total_mass_kg
        breakeven_rows.append({
            "threshold_pct": threshold_pct,
            "cf_al_breakeven_kgco2e_per_kg": round(cf_breakeven, 2),
            "interpretation": (
                f"Manufacturing reaches {threshold_pct:.0f}% of total footprint "
                f"when aluminum CF drops to {cf_breakeven:.2f} kg CO2e/kg "
                f"(at Indiana grid {INDIANA_GRID_CI} kg CO2e/kWh)"
            ),
        })
    result["breakeven_df"] = pd.DataFrame(breakeven_rows)

    return result


def plot(r: dict) -> None:
    import matplotlib.pyplot as plt
    apply_style()

    # ---- 2D contour: manufacturing share vs (CF_al, grid CI) ----
    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    levels = [2, 5, 10, 20, 40]
    cs = ax.contourf(r["CF_GRID"], r["CI_GRID"], r["mfg_share_grid"],
                     levels=[0] + levels + [100],
                     colors=["#f7fbff", "#c6dbef", "#9ecae1",
                             "#6baed6", "#3182bd", "#08519c"])
    cl = ax.contour(r["CF_GRID"], r["CI_GRID"], r["mfg_share_grid"],
                    levels=levels, colors="white", linewidths=0.7)
    ax.clabel(cl, fmt="%d%%", fontsize=6)

    # Mark our operating point (Indiana grid, virgin aluminum)
    ax.plot(CF_SCENARIOS["Virgin (global avg)"], INDIANA_GRID_CI,
            marker="*", color="yellow", markersize=10, label="Our baseline")
    ax.plot(CF_SCENARIOS["Recycled (secondary)"], INDIANA_GRID_CI,
            marker="D", color="orange", markersize=7, label="Recycled Al")

    ax.set_xlabel("Aluminum CF (kg CO2e / kg)")
    ax.set_ylabel("Grid CI (kg CO2e / kWh)")
    ax.set_title("Manufacturing share of total footprint")
    ax.legend(fontsize=6)

    cbar = fig.colorbar(cs, ax=ax)
    cbar.set_label("Mfg share (%)", fontsize=7)

    save_fig(fig, str(OUT / "B1_breakeven_contour"))

    # ---- 1D: manufacturing share vs aluminum CF at fixed grid ----
    cf_range = np.linspace(0.3, 17, 200)
    e_mfg = r["total_energy_kwh"] * INDIANA_GRID_CI
    e_mat = r["total_mass_kg"] * cf_range
    share_1d = e_mfg / (e_mat + e_mfg) * 100

    fig2, ax2 = plt.subplots()
    ax2.plot(cf_range, share_1d, color=COLORS[0])
    for threshold, ls in [(2, ":"), (5, "--"), (10, "-.")]:
        ax2.axhline(threshold, color="gray", linestyle=ls, linewidth=0.8,
                    label=f"{threshold}%")
    for name, cf_val in CF_SCENARIOS.items():
        ax2.axvline(cf_val, color=COLORS[2], linestyle=":", linewidth=0.6, alpha=0.7)
        ax2.text(cf_val, share_1d[np.argmin(np.abs(cf_range - cf_val))] + 0.3,
                 name.split("(")[0].strip()[:12], fontsize=5, rotation=90, va="bottom")
    ax2.set_xlabel("Aluminum CF (kg CO2e / kg)")
    ax2.set_ylabel("Manufacturing share of total footprint (%)")
    ax2.set_title(f"Break-even analysis (Indiana grid {INDIANA_GRID_CI} kg CO2e/kWh)")
    ax2.legend(title="Threshold", fontsize=6)
    save_fig(fig2, str(OUT / "B1_breakeven_1d"))


def write_findings(r: dict) -> None:
    r["scenario_df"].to_csv(OUT / "B1_scenarios.csv", index=False)
    r["breakeven_df"].to_csv(OUT / "B1_breakeven_thresholds.csv", index=False)

    energy_note = ("" if ENERGY_VERIFIED else
                   "\nNOTE: Total energy values are context doc estimates. "
                   "Update TOTAL_ENERGY_WH from estimation_ladder/outputs/summary_by_part.csv "
                   "after running that project.")
    mass_note = ("\nNOTE: Stock masses are owner-verified from bom.csv "
                 "(body 1880 g, lid 518 g). Earlier drafts used estimates of "
                 "2500 g and 610 g; the smaller verified stock lowers the "
                 "materials term and RAISES the manufacturing share vs old numbers."
                 if MASS_VERIFIED else
                 "\nNOTE: Stock masses are estimates. "
                 "Update STOCK_MASS_G from bom.csv once verified.")

    scen_lines = ["| Scenario | CF (kg CO2e/kg) | E_mat | E_mfg | Mfg share |",
                  "|---|---|---|---|---|"]
    for _, row in r["scenario_df"].iterrows():
        scen_lines.append(
            f"| {row['scenario']} | {row['cf_al_kgco2e_per_kg']} | "
            f"{row['e_materials_kgco2e']:.2f} | {row['e_manufacturing_kgco2e']:.4f} | "
            f"{row['manufacturing_share_pct']:.2f}% |"
        )
    scen_table = "\n".join(scen_lines)

    be_lines = ["| Threshold | CF_al at break-even | Note |", "|---|---|---|"]
    for _, row in r["breakeven_df"].iterrows():
        be_lines.append(
            f"| {row['threshold_pct']:.0f}% | "
            f"{row['cf_al_breakeven_kgco2e_per_kg']:.2f} kg CO2e/kg | "
            f"{row['interpretation'][:60]}... |"
        )
    be_table = "\n".join(be_lines)

    findings_text = (
        "# B1_breakeven: findings\n\n"
        "**Status:** explored\n"
        f"**Date:** {pd.Timestamp.today().date()}\n\n"
        "## Headline\n"
        "The 'materials dominate' conclusion (~98% of footprint) is conditional on aluminum\n"
        "source. At virgin aluminum (global average ~12 kg CO2e/kg) and Indiana grid\n"
        f"({INDIANA_GRID_CI} kg CO2e/kWh), manufacturing is "
        f"~{r['scenario_df'].loc[r['scenario_df']['scenario'].str.contains('global avg'), 'manufacturing_share_pct'].values[0]:.1f}% "
        "of total footprint. At secondary (recycled) aluminum (~0.5 kg CO2e/kg), manufacturing\n"
        "can exceed 20%. This converts the paper's limitation into a forward argument:\n"
        "decarbonizing aluminum is exactly what makes operation-level monitoring start to matter.\n\n"
        "## Numbers\n\n"
        "### Manufacturing share by aluminum scenario (Indiana grid fixed)\n"
        f"{scen_table}\n\n"
        "### Break-even thresholds (at what CF_al does manufacturing reach threshold?)\n"
        f"{be_table}\n\n"
        "## Verification\n\n"
        f"{log.to_markdown()}\n"
        f"{energy_note}\n{mass_note}\n\n"
        "## Caveats\n"
        "- Total energy is summed across body and lid CNC machining only (AM parts excluded).\n"
        "- Stock masses are owner-verified (bom.csv); energy totals remain estimates until\n"
        "  estimation_ladder runs on the measurement CSVs.\n"
        "- Grid carbon intensity (Indiana/MISO) is an approximate annual average.\n"
        "  Marginal/hourly intensity from WattTime MOER would sharpen this.\n"
        "- This is a parametric exhibit, not a sensitivity analysis of measured uncertainty.\n\n"
        "## Feeds the journal paper?\n"
        "Yes -- strong Discussion paragraph. Converts the '98% materials' finding from a\n"
        "limitation into a forward argument. Shows why the measurement capability this paper\n"
        "establishes will matter more as aluminum decarbonizes. Produces a citable figure.\n\n"
        "## How to extend\n"
        "- Replace TOTAL_ENERGY_WH with verified values from estimation_ladder.\n"
        "- Replace INDIANA_GRID_CI with MOER-derived marginal intensity once available.\n"
    )
    (Path(__file__).parent / "B1_breakeven_FINDINGS.md").write_text(findings_text)
    print(f"Findings written to explorations/B1_breakeven_FINDINGS.md")


def main() -> None:
    r = compute()

    # Print point-estimate table
    print("\nManufacturing share by aluminum scenario (Indiana grid):")
    print(r["scenario_df"][["scenario", "manufacturing_share_pct"]].to_string(index=False))
    print("\nBreak-even thresholds:")
    for _, row in r["breakeven_df"].iterrows():
        print(f"  {row['threshold_pct']:.0f}%: {row['interpretation']}")

    if log.any_disagreements():
        print("\nWARNING: a cross-check disagreed -- see findings for details")

    plot(r)
    write_findings(r)
    print("\nOK  -- figures in explorations/outputs/")


if __name__ == "__main__":
    main()
