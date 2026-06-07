"""
ch3_extended_decarbonization_trajectory.py — Is scheduling becoming more or less valuable?

Tracks year-over-year changes in mean MOER, intra-day variability, and scheduling
opportunity across 2022-2024 to determine whether grid decarbonization amplifies
or diminishes the value of carbon-aware scheduling.

Research question:
    "As grids add more renewables, is carbon-aware scheduling becoming
    more or less valuable over time?"

Outputs:
    Figures:
        fig_ext_trajectory_summary.png/pdf
        fig_ext_duck_curve_evolution.png/pdf
        fig_ext_scheduling_opportunity_trend.png/pdf
    Tables:
        table_ext_trajectory.csv/md

Usage:
    python ch3_extended_decarbonization_trajectory.py
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min,
    run_scheduling_sim, compute_thresholds,
    CH3_REGIONS, REGION_COLORS, SEASON_ORDER, SEASON_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR,
)


# =============================================================================
# ANALYSIS 1 — YEAR-OVER-YEAR METRICS
# =============================================================================

def compute_annual_metrics(df_5min):
    """Track mean MOER, daily IQR, CV, and TL savings by year and region."""
    print("\n── Annual metrics ──")

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START)
        & (df_5min["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]

        for year in sorted(rd["year"].unique()):
            yd = rd[rd["year"] == year]
            if len(yd) < 1000:
                continue

            daily = yd.groupby("date")["value"].agg(["mean", "std", "min", "max",
                                                       lambda x: x.quantile(0.75) - x.quantile(0.25)])
            daily.columns = ["mean", "std", "min", "max", "iqr"]

            rows.append({
                "region": region, "year": year,
                "mean_moer": yd["value"].mean(),
                "median_daily_iqr": daily["iqr"].median(),
                "mean_daily_range": (daily["max"] - daily["min"]).mean(),
                "cv": yd["value"].std() / yd["value"].mean(),
                "n_days": len(daily),
            })

    df = pd.DataFrame(rows)

    # Record trends
    for region in CH3_REGIONS:
        rd = df[df["region"] == region].sort_values("year")
        if len(rd) < 2:
            continue
        moer_change = rd["mean_moer"].iloc[-1] - rd["mean_moer"].iloc[0]
        iqr_change = rd["median_daily_iqr"].iloc[-1] - rd["median_daily_iqr"].iloc[0]
        iqr_pct_change = iqr_change / rd["median_daily_iqr"].iloc[0] * 100 if rd["median_daily_iqr"].iloc[0] > 0 else 0

        record_number("Trajectory", f"{rshort(region)} mean MOER change", moer_change, "+.0f")
        record_number("Trajectory", f"{rshort(region)} IQR change %", iqr_pct_change, "+.1f")
        record_number("Trajectory", f"{rshort(region)} IQR direction",
                      "increasing" if iqr_change > 0 else "decreasing")

    save_table(df, "table_ext_trajectory",
               "Year-over-year grid metrics during manufacturing hours.")
    return df


def plot_trajectory_summary(metrics_df):
    """2×3 faceted: mean MOER + daily IQR trends by region."""
    print("\n── Fig: Trajectory summary ──")

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 8))
        axes = axes.flatten()

        for i, region in enumerate(CH3_REGIONS):
            ax = axes[i]
            rd = metrics_df[metrics_df["region"] == region].sort_values("year")
            if len(rd) == 0:
                ax.set_title(rshort(region))
                continue

            ax2 = ax.twinx()

            ax.plot(rd["year"], rd["mean_moer"], "o-", color="#4575b4",
                    linewidth=2, markersize=7, label="Mean MOER")
            ax2.plot(rd["year"], rd["median_daily_iqr"], "s--", color="#d73027",
                     linewidth=2, markersize=7, label="Daily IQR")

            ax.set_title(rshort(region), fontsize=11)
            ax.set_ylabel(f"Mean MOER", color="#4575b4", fontsize=9)
            ax2.set_ylabel("Daily IQR", color="#d73027", fontsize=9)
            ax.set_xticks(rd["year"].values)

            if i == 0:
                lines1, labels1 = ax.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                ax.legend(lines1 + lines2, labels1 + labels2, fontsize=7, loc="upper right")

        plt.tight_layout()
        save_fig(fig, "fig_ext_trajectory_summary")


# =============================================================================
# ANALYSIS 2 — DUCK CURVE EVOLUTION (CAISO)
# =============================================================================

def plot_duck_curve_evolution(df_5min):
    """CAISO diurnal profile overlaid for each year — show duck curve deepening."""
    print("\n── Fig: Duck curve evolution ──")

    caiso = df_5min[df_5min["region"] == "CAISO_NORTH"]
    if len(caiso) == 0:
        print("  ⚠️ No CAISO data")
        return

    year_colors = {2022: "#fc8d59", 2023: "#91bfdb", 2024: "#4575b4"}

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 5))

        for year in sorted(caiso["year"].unique()):
            yd = caiso[caiso["year"] == year]
            hourly = yd.groupby("hour")["value"].mean()
            color = year_colors.get(year, "#333333")
            ax.plot(hourly.index, hourly.values, linewidth=2.5, color=color,
                    label=str(year), marker="o", markersize=4)

        ax.axvspan(DAY_SHIFT_START, DAY_SHIFT_END, alpha=0.05, color="green")
        ax.set_xlabel("Hour of Day (Local Time)")
        ax.set_ylabel(f"Mean MOER ({SIGNAL_UNIT})")
        ax.set_xlim(0, 23)
        ax.set_xticks(range(0, 24, 3))
        ax.legend(fontsize=10, title="Year")

        # Annotate duck curve metrics
        for year in sorted(caiso["year"].unique()):
            yd = caiso[caiso["year"] == year]
            hourly = yd.groupby("hour")["value"].mean()
            trough = hourly.loc[10:14].min()
            peak = hourly.loc[17:21].max()
            duck_depth = peak - trough
            record_number("Trajectory", f"CAISO {year} duck depth", duck_depth, ".0f")

        save_fig(fig, "fig_ext_duck_curve_evolution")


# =============================================================================
# ANALYSIS 3 — SCHEDULING OPPORTUNITY INDEX TREND
# =============================================================================

def compute_scheduling_opportunity_trend(df_5min):
    """
    Scheduling opportunity index = median daily IQR during manufacturing hours.
    Track by year × season to control for weather confounding.
    """
    print("\n── Scheduling opportunity trend ──")

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START)
        & (df_5min["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        for year in sorted(rd["year"].unique()):
            for season in SEASON_ORDER:
                sd = rd[(rd["year"] == year) & (rd["season"] == season)]
                if len(sd) < 100:
                    continue
                daily_iqr = sd.groupby("date")["value"].apply(
                    lambda x: x.quantile(0.75) - x.quantile(0.25)
                )
                rows.append({
                    "region": region, "year": year, "season": season,
                    "median_iqr": daily_iqr.median(),
                    "mean_iqr": daily_iqr.mean(),
                    "n_days": len(daily_iqr),
                })

    return pd.DataFrame(rows)


def plot_opportunity_trend(opp_df):
    """Line plot: scheduling opportunity index by year, one line per region."""
    print("\n── Fig: Scheduling opportunity trend ──")

    # Annual average (across seasons)
    annual = opp_df.groupby(["region", "year"])["median_iqr"].mean().reset_index()

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for region in CH3_REGIONS:
            rd = annual[annual["region"] == region].sort_values("year")
            if len(rd) == 0:
                continue
            ax.plot(rd["year"], rd["median_iqr"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=8, linewidth=2, label=rshort(region))

        ax.set_xlabel("Year")
        ax.set_ylabel(f"Scheduling Opportunity Index\n(median daily IQR, {SIGNAL_UNIT})")
        ax.set_xticks(sorted(annual["year"].unique()))
        ax.legend(fontsize=9)

        save_fig(fig, "fig_ext_scheduling_opportunity_trend")

    # Count regions where opportunity is increasing
    increasing = 0
    for region in CH3_REGIONS:
        rd = annual[annual["region"] == region].sort_values("year")
        if len(rd) >= 2 and rd["median_iqr"].iloc[-1] > rd["median_iqr"].iloc[0]:
            increasing += 1
    record_number("Trajectory", f"Regions with increasing opportunity", f"{increasing}/{len(CH3_REGIONS)}")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()

    metrics = compute_annual_metrics(df_5min)
    plot_trajectory_summary(metrics)
    plot_duck_curve_evolution(df_5min)

    opp_df = compute_scheduling_opportunity_trend(df_5min)
    plot_opportunity_trend(opp_df)

    export_numbers()
    print("\n✅ Decarbonization trajectory analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
