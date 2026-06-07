"""
ch3_extended_economic_value.py — What's the dollar value of carbon-aware scheduling?

Converts scheduling savings to tonnes CO₂/year and $/year under carbon price
scenarios. Computes marginal abatement cost and checks TOU rate co-benefits.

Research question:
    "What's this worth in dollars, and how does scheduling compare to other
    decarbonization investments?"

Outputs:
    Figures:
        fig_ext_annual_savings.png/pdf
        fig_ext_carbon_value.png/pdf
    Tables:
        table_ext_economic_value.csv/md

Usage:
    python ch3_extended_economic_value.py
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min,
    run_scheduling_sim, compute_thresholds, compute_annual_tonnes,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR,
)


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

# Carbon price scenarios ($/tonne CO₂)
CARBON_PRICES = {
    "Voluntary market":  50,
    "EU ETS (~2024)":    70,
    "IEA Net Zero":      100,
    "EPA Social Cost":   185,
}

# Facility size scenarios
FACILITY_SCENARIOS = {
    "Small CNC shop":     {"jobs_per_day": 50,  "kwh_per_job": 0.755, "desc": "10 machines, oil-pump-type parts"},
    "Medium manufacturer": {"jobs_per_day": 100, "kwh_per_job": 2.0,   "desc": "Reference facility"},
    "Large plant":         {"jobs_per_day": 500, "kwh_per_job": 2.0,   "desc": "High-volume production"},
    "AM farm":             {"jobs_per_day": 20,  "kwh_per_job": 5.0,   "desc": "3D print farm, long jobs"},
}

WORKING_DAYS_PER_YEAR = 250

# CAISO TOU rate structure (approximate PG&E E-20, $/kWh)
# These are rough approximations for co-benefit analysis
CAISO_TOU_RATES = {
    "off_peak":       0.10,   # 21:00-08:00
    "partial_peak":   0.15,   # 08:00-12:00, 18:00-21:00
    "on_peak":        0.25,   # 12:00-18:00 (summer only, but use as proxy)
}
CAISO_TOU_HOURS = {
    "off_peak": list(range(0, 8)) + list(range(21, 24)),
    "partial_peak": list(range(8, 12)) + list(range(18, 21)),
    "on_peak": list(range(12, 18)),
}


# =============================================================================
# ANALYSIS 1 — ANNUAL TONNAGE & DOLLAR VALUE
# =============================================================================

def compute_economic_value(df_5min):
    """Compute annual emissions avoided and dollar value by region and scenario."""
    print("\n── Economic value computation ──")

    thresholds = compute_thresholds(df_5min)
    sim = run_scheduling_sim(df_5min, thresholds=thresholds, use_cache=True, cache_tag="econ_sim")

    rows = []
    for region in CH3_REGIONS:
        rd = sim[sim["region"] == region]
        if len(rd) == 0:
            continue

        mean_tl_savings_pct = rd["savings_tl_pct"].mean()
        mean_baseline_moer = rd["baseline_moer"].mean()
        mean_tl_moer = rd[f"tl_{TL_STRATEGY}_moer"].mean() if f"tl_{TL_STRATEGY}_moer" in rd.columns else rd["traffic_light_moer"].mean()
        savings_moer = mean_baseline_moer - mean_tl_moer  # lbs/MWh saved

        for fac_name, fac in FACILITY_SCENARIOS.items():
            annual_tonnes = compute_annual_tonnes(
                savings_moer,
                job_kwh=fac["kwh_per_job"],
                units=fac["jobs_per_day"],
                days=WORKING_DAYS_PER_YEAR,
            )

            for price_name, price in CARBON_PRICES.items():
                annual_dollars = annual_tonnes * price

                rows.append({
                    "region": region,
                    "facility": fac_name,
                    "carbon_price_scenario": price_name,
                    "carbon_price_per_tonne": price,
                    "jobs_per_day": fac["jobs_per_day"],
                    "kwh_per_job": fac["kwh_per_job"],
                    "tl_savings_pct": mean_tl_savings_pct,
                    "savings_moer_lbs_mwh": savings_moer,
                    "annual_tonnes_avoided": annual_tonnes,
                    "annual_dollars": annual_dollars,
                })

    df = pd.DataFrame(rows)

    # Record key numbers for reference facility at $100/t
    ref_rows = df[(df["facility"] == "Medium manufacturer") & (df["carbon_price_per_tonne"] == 100)]
    for _, row in ref_rows.iterrows():
        record_number("Economic", f"{rshort(row['region'])} annual tonnes avoided",
                      row["annual_tonnes_avoided"], ".2f")
        record_number("Economic", f"{rshort(row['region'])} annual $ at $100/t",
                      row["annual_dollars"], ".0f")

    save_table(df, "table_ext_economic_value",
               "Economic value of carbon-aware scheduling by region, facility, and carbon price.")
    return df


def plot_annual_savings(econ_df):
    """Bar chart: tonnes CO₂/year and $/year for reference facility."""
    print("\n── Fig: Annual savings ──")

    ref = econ_df[(econ_df["facility"] == "Medium manufacturer") &
                  (econ_df["carbon_price_per_tonne"] == 100)]

    with thesis_style():
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        regions = list(CH3_REGIONS.keys())
        ref = ref.set_index("region").reindex(regions)
        x = np.arange(len(regions))

        # Left: tonnes
        bars1 = ax1.bar(x, ref["annual_tonnes_avoided"],
                        color=[rcolor(r) for r in regions], edgecolor="white")
        ax1.set_xticks(x)
        ax1.set_xticklabels([rshort(r) for r in regions], fontsize=9)
        ax1.set_ylabel("Annual CO₂ Avoided (tonnes)")
        ax1.set_title("Reference Facility: 100 jobs/day × 2 kWh")
        for bar, val in zip(bars1, ref["annual_tonnes_avoided"]):
            if val > 0:
                ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                         f"{val:.2f}", ha="center", fontsize=8)

        # Right: dollars at multiple price points
        w = 0.18
        for j, (price_name, price) in enumerate(CARBON_PRICES.items()):
            price_data = econ_df[(econ_df["facility"] == "Medium manufacturer") &
                                 (econ_df["carbon_price_per_tonne"] == price)]
            price_data = price_data.set_index("region").reindex(regions)
            ax2.bar(x + j * w, price_data["annual_dollars"], w,
                    label=f"${price}/t", alpha=0.85, edgecolor="white")

        ax2.set_xticks(x + 1.5 * w)
        ax2.set_xticklabels([rshort(r) for r in regions], fontsize=9)
        ax2.set_ylabel("Annual Value ($)")
        ax2.set_title("Dollar Value by Carbon Price Scenario")
        ax2.legend(fontsize=8)

        plt.tight_layout()
        save_fig(fig, "fig_ext_carbon_value")


# =============================================================================
# ANALYSIS 2 — MARGINAL ABATEMENT COST
# =============================================================================

def compute_abatement_cost(econ_df):
    """The heuristic costs ~$0 to implement → abatement cost ≈ $0/tonne."""
    print("\n── Marginal abatement cost ──")

    ref = econ_df[(econ_df["facility"] == "Medium manufacturer") &
                  (econ_df["carbon_price_per_tonne"] == 100)]

    for _, row in ref.iterrows():
        # Implementation cost ≈ $0 (schedule change only)
        # So abatement cost = $0 / tonnes = $0/tonne
        record_number("Economic",
                      f"{rshort(row['region'])} abatement cost ($/tonne)",
                      "≈$0 (schedule change)")


# =============================================================================
# ANALYSIS 3 — TOU RATE CO-BENEFIT (CAISO ONLY)
# =============================================================================

def analyze_tou_cobenefit(df_5min):
    """Check if low-MOER hours align with low-TOU-rate hours in CAISO."""
    print("\n── TOU rate co-benefit (CAISO) ──")

    caiso = df_5min[
        (df_5min["region"] == "CAISO_NORTH")
        & (df_5min["hour"] >= DAY_SHIFT_START)
        & (df_5min["hour"] < DAY_SHIFT_END)
    ]
    if len(caiso) == 0:
        print("  ⚠️ No CAISO data")
        return

    # Assign TOU rate to each interval
    def get_tou_rate(hour):
        for period, hours in CAISO_TOU_HOURS.items():
            if hour in hours:
                return CAISO_TOU_RATES[period]
        return CAISO_TOU_RATES["partial_peak"]

    caiso_hourly = caiso.groupby("hour")["value"].mean()

    # Correlation between hourly MOER and TOU rate
    hours = list(range(DAY_SHIFT_START, DAY_SHIFT_END))
    moer_vals = [caiso_hourly.get(h, np.nan) for h in hours]
    tou_vals = [get_tou_rate(h) for h in hours]

    valid = [(m, t) for m, t in zip(moer_vals, tou_vals) if not np.isnan(m)]
    if len(valid) > 3:
        corr = np.corrcoef([v[0] for v in valid], [v[1] for v in valid])[0, 1]
        record_number("Economic", "CAISO MOER-TOU rate correlation", corr, ".2f")

        if corr < -0.3:
            record_number("Economic", "CAISO TOU alignment", "Favorable (low MOER ≈ low rate)")
        elif corr > 0.3:
            record_number("Economic", "CAISO TOU alignment", "Unfavorable (low MOER ≈ high rate)")
        else:
            record_number("Economic", "CAISO TOU alignment", "Weak alignment")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()

    econ_df = compute_economic_value(df_5min)
    plot_annual_savings(econ_df)
    compute_abatement_cost(econ_df)
    analyze_tou_cobenefit(df_5min)

    export_numbers()
    print("\n✅ Economic value analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
