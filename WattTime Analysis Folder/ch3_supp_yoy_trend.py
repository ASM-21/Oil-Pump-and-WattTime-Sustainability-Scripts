"""
ch3_supp_yoy_trend.py — Year-over-year MOER trend analysis (Section 2.1).

Detects whether MOER is trending over the study period in each archetype.
Uses Mann-Kendall test on monthly means for statistical power.

Outputs (ch3supp/):
    Tables:
        table_supp_yoy_annual_stats.csv / .md
        table_supp_yoy_trend_test.csv / .md
    Figures:
        fig_supp_yoy_annual_mean.png / .pdf
        fig_supp_yoy_optimal_savings.png / .pdf

Usage:
    python ch3_supp_yoy_trend.py
    python ch3_supp_yoy_trend.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci, compute_thresholds,
    CH3_REGIONS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    rshort, rcolor, rmarker,
    save_cache, load_cache,
)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
CACHE_VERSION = 1

SUPP_DIR     = Path(__file__).parent / "ch3supp"
SUPP_FIGURES = SUPP_DIR / "figures"
SUPP_TABLES  = SUPP_DIR / "tables"
SUPP_NUMBERS = SUPP_DIR / "ch3_supp_numbers.md"
# ▲▲▲ END CONFIG ▲▲▲

ch3_common.FIGURES_DIR  = SUPP_FIGURES
ch3_common.TABLES_DIR   = SUPP_TABLES
ch3_common.NUMBERS_FILE = SUPP_NUMBERS
SUPP_FIGURES.mkdir(parents=True, exist_ok=True)
SUPP_TABLES.mkdir(parents=True, exist_ok=True)


# =============================================================================
# MANN-KENDALL TEST (implemented without scipy dependency)
# =============================================================================

def mann_kendall(x):
    """
    Mann-Kendall trend test.
    Returns: tau, p_value, sens_slope
    """
    x = np.array(x, dtype=float)
    n = len(x)
    if n < 4:
        return np.nan, np.nan, np.nan

    # S statistic
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = x[j] - x[i]
            if diff > 0:   s += 1
            elif diff < 0: s -= 1

    # Variance of S (no ties handling for simplicity)
    var_s = n * (n - 1) * (2 * n + 5) / 18

    # Z statistic
    if s > 0:   z = (s - 1) / np.sqrt(var_s)
    elif s < 0: z = (s + 1) / np.sqrt(var_s)
    else:       z = 0.0

    # Two-sided p-value via normal approximation
    from math import erfc, sqrt
    p_value = erfc(abs(z) / sqrt(2))

    # Kendall's tau
    tau = s / (n * (n - 1) / 2)

    # Sen's slope: median of all pairwise slopes
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            if j != i:
                slopes.append((x[j] - x[i]) / (j - i))
    sens_slope = float(np.median(slopes)) if slopes else np.nan

    return float(tau), float(p_value), sens_slope


# =============================================================================
# ANNUAL STATISTICS
# =============================================================================

def compute_annual_stats(df_5min, thresholds, recompute=False):
    cache_tag    = "supp_yoy_annual"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for region in CH3_REGIONS:
        rd = df_5min[df_5min["region"] == region]
        rd_win = window[window["region"] == region]
        gt, rt = td.get(region, (np.inf, np.inf))

        for year in sorted(rd["year"].unique()):
            yd     = rd[rd["year"] == year]["value"]
            yd_win = rd_win[rd_win["year"] == year]

            if len(yd) == 0:
                continue

            # Optimal savings per day
            opt_savings = []
            for date, ddf in yd_win.groupby("date"):
                vals = ddf.sort_values("point_time_local")["value"].values
                sim  = simulate_day(vals, job_intervals, gt, rt)
                if sim is None or sim["baseline_moer"] <= 0:
                    continue
                opt_savings.append(
                    (sim["baseline_moer"] - sim["optimal_moer"])
                    / sim["baseline_moer"] * 100
                )

            rows.append({
                "region":         region,
                "region_short":   rshort(region),
                "year":           int(year),
                "annual_mean":    float(yd.mean()),
                "annual_median":  float(yd.median()),
                "annual_std":     float(yd.std()),
                "annual_p25":     float(yd.quantile(0.25)),
                "annual_p75":     float(yd.quantile(0.75)),
                "daily_range":    float(
                    rd[rd["year"] == year].groupby("date")["value"]
                    .agg(lambda x: x.max() - x.min()).mean()
                ),
                "optimal_savings": float(np.mean(opt_savings)) if opt_savings else np.nan,
                "n_days":         int(yd_win.groupby("date").ngroups),
            })

    df = pd.DataFrame(rows)
    save_cache(df, cache_tag, cache_params)
    return df


# =============================================================================
# TREND TEST ON MONTHLY MEANS
# =============================================================================

def compute_trend_tests(df_5min, thresholds, recompute=False):
    cache_tag    = "supp_yoy_trend"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for region in CH3_REGIONS:
        rd     = df_5min[df_5min["region"] == region]
        rd_win = window[window["region"] == region]
        gt, rt = td.get(region, (np.inf, np.inf))

        # Monthly mean MOER
        monthly = (rd.groupby(["year", "month"])["value"].mean()
                   .reset_index().sort_values(["year", "month"]))
        if len(monthly) < 4:
            continue

        tau_m, p_m, slope_m = mann_kendall(monthly["value"].values)

        # Monthly optimal savings
        daily_opt = []
        for date, ddf in rd_win.groupby("date"):
            vals = ddf.sort_values("point_time_local")["value"].values
            sim  = simulate_day(vals, job_intervals, gt, rt)
            if sim is None or sim["baseline_moer"] <= 0:
                continue
            daily_opt.append({
                "year":  ddf["year"].iloc[0],
                "month": ddf["month"].iloc[0],
                "opt":   (sim["baseline_moer"] - sim["optimal_moer"]) / sim["baseline_moer"] * 100,
            })

        if daily_opt:
            opt_df = pd.DataFrame(daily_opt)
            monthly_opt = (opt_df.groupby(["year", "month"])["opt"].mean()
                           .reset_index().sort_values(["year", "month"]))
            tau_o, p_o, slope_o = mann_kendall(monthly_opt["opt"].values)
        else:
            tau_o, p_o, slope_o = np.nan, np.nan, np.nan

        # Sen's slope in lbs/MWh per year (monthly slope × 12)
        annual_slope = slope_m * 12 if not np.isnan(slope_m) else np.nan

        rows.append({
            "region":            region,
            "region_short":      rshort(region),
            "moer_tau":          tau_m,
            "moer_p_value":      p_m,
            "moer_sens_slope_mo": slope_m,
            "moer_annual_slope": annual_slope,
            "opt_tau":           tau_o,
            "opt_p_value":       p_o,
            "opt_annual_slope":  slope_o * 12 if not np.isnan(slope_o) else np.nan,
            "n_months":          len(monthly),
        })

    df = pd.DataFrame(rows)
    save_cache(df, cache_tag, cache_params)
    return df


# =============================================================================
# FIGURES
# =============================================================================

def plot_annual_mean(annual_stats):
    print("\n── Fig: Annual mean MOER ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(8, 5))
        for region in CH3_REGIONS:
            rd = annual_stats[annual_stats["region"] == region].sort_values("year")
            if len(rd) == 0:
                continue
            ax.plot(rd["year"], rd["annual_mean"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=7, linewidth=2, label=rshort(region))
            ax.fill_between(rd["year"],
                            rd["annual_p25"], rd["annual_p75"],
                            color=rcolor(region), alpha=0.10)

        ax.set_xlabel("Year")
        ax.set_ylabel(f"Annual Mean MOER ({SIGNAL_UNIT})")
        ax.set_xticks(sorted(annual_stats["year"].unique()))
        ax.legend(fontsize=9)
        fig.suptitle("Annual Mean MOER by Archetype\nShaded band = P25–P75", fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_yoy_annual_mean")


def plot_optimal_savings_trend(annual_stats):
    print("\n── Fig: Annual optimal savings trend ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(8, 5))
        for region in CH3_REGIONS:
            rd = annual_stats[annual_stats["region"] == region].sort_values("year")
            if len(rd) == 0:
                continue
            ax.plot(rd["year"], rd["optimal_savings"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=7, linewidth=2, label=rshort(region))

        ax.axhline(0, color="black", linewidth=0.7)
        ax.set_xlabel("Year")
        ax.set_ylabel("Mean Optimal Savings vs. Baseline (%)")
        ax.set_xticks(sorted(annual_stats["year"].unique()))
        ax.legend(fontsize=9)
        fig.suptitle("Annual Scheduling Opportunity (Optimal Savings) by Archetype",
                     fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_yoy_optimal_savings")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Year-Over-Year MOER Trend Analysis")
    print("="*60)

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)

    annual_stats = compute_annual_stats(df_5min, thresholds, recompute)
    trend_tests  = compute_trend_tests(df_5min, thresholds, recompute)

    print("\nTrend test results:")
    print(trend_tests[["region_short", "moer_p_value",
                        "moer_annual_slope", "opt_p_value"]].to_string(index=False))

    save_table(annual_stats.round(2), "table_supp_yoy_annual_stats",
               caption="Annual MOER statistics by archetype and year.")
    save_table(trend_tests.round(4), "table_supp_yoy_trend_test",
               caption=(
                   "Mann-Kendall trend test on monthly mean MOER. "
                   "Slope in lbs/MWh per year (Sen's slope). "
                   "p < 0.05 indicates statistically significant trend."
               ))

    plot_annual_mean(annual_stats)
    plot_optimal_savings_trend(annual_stats)

    sec = "Supp: YoY Trend"
    for _, row in trend_tests.iterrows():
        s = row["region_short"]
        record_number(sec, f"{s} MOER annual slope (lbs/yr)", row["moer_annual_slope"], "+.1f")
        record_number(sec, f"{s} MOER trend p-value", row["moer_p_value"], ".3f")
    export_numbers()
    print("\n✅ ch3_supp_yoy_trend complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
