"""
ch3_supp_monthly_savings.py — Monthly savings consistency (Section 2.5).

Outputs (ch3supp/):
    Tables:
        table_supp_monthly_savings.csv / .md
    Figures:
        fig_supp_monthly_heatmap.png / .pdf
        fig_supp_monthly_lines.png / .pdf

Usage:
    python ch3_supp_monthly_savings.py
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci, compute_thresholds,
    CH3_REGIONS,
    DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rshort, rcolor,
    save_cache, load_cache,
)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
CACHE_VERSION = 1
MONTH_LABELS  = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

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


def compute_monthly_savings(df_5min, thresholds, recompute=False):
    cache_tag    = "supp_monthly_savings"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key        = f"tl_{TL_STRATEGY}_moer"
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    # Best hour per region per season (for seasonal TOD — "best practical")
    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]

    seasonal_best = {}
    for region in CH3_REGIONS:
        rd = window[window["region"] == region]
        seasonal_best[region] = {}
        for season in rd["season"].unique():
            sd = rd[rd["season"] == season]
            hm = sd.groupby("hour")["value"].mean()
            seasonal_best[region][season] = int(hm.idxmin())

    rows = []
    for region in CH3_REGIONS:
        gt, rt = td.get(region, (np.inf, np.inf))
        rd = window[window["region"] == region]

        for date, ddf in rd.groupby("date"):
            vals   = ddf.sort_values("point_time_local")["value"].values
            sim    = simulate_day(vals, job_intervals, gt, rt)
            if sim is None or sim["baseline_moer"] <= 0:
                continue

            baseline = sim["baseline_moer"]
            season   = ddf["season"].iloc[0]
            bh       = seasonal_best[region].get(season, DAY_SHIFT_START)
            idx      = (bh - DAY_SHIFT_START) * INTERVALS_PER_HOUR

            tod_moer = (float(np.mean(vals[idx: idx + job_intervals]))
                        if idx + job_intervals <= len(vals)
                        else baseline)
            tl_moer  = sim[tl_key]

            best_moer    = min(tod_moer, tl_moer)
            best_savings = (baseline - best_moer) / baseline * 100

            rows.append({
                "region":       region,
                "date":         date,
                "month":        ddf["month"].iloc[0],
                "savings":      best_savings,
            })

    df = pd.DataFrame(rows)
    save_cache(df, cache_tag, cache_params)
    return df


def aggregate_monthly(daily_df):
    rows = []
    for region in CH3_REGIONS:
        rd = daily_df[daily_df["region"] == region]
        for month in range(1, 13):
            md = rd[rd["month"] == month]["savings"].values
            if len(md) == 0:
                continue
            lo, hi = bootstrap_ci(md)
            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "month":        month,
                "month_label":  MONTH_LABELS[month - 1],
                "mean_savings": round(float(np.mean(md)), 2),
                "ci_lo":        round(lo, 2),
                "ci_hi":        round(hi, 2),
                "std_savings":  round(float(np.std(md)), 2),
                "n_days":       len(md),
                "is_backfire":  float(np.mean(md)) < 0,
            })
    return pd.DataFrame(rows)


def plot_heatmap(monthly_agg):
    print("\n── Fig: Monthly savings heatmap ──")
    regions = list(CH3_REGIONS.keys())
    months  = range(1, 13)

    matrix = pd.DataFrame(index=[rshort(r) for r in regions],
                           columns=MONTH_LABELS, dtype=float)
    for _, row in monthly_agg.iterrows():
        matrix.loc[rshort(row["region"]), MONTH_LABELS[row["month"] - 1]] = row["mean_savings"]

    vals     = matrix.values.astype(float)
    abs_max  = np.nanmax(np.abs(vals))
    norm     = mcolors.TwoSlopeNorm(vmin=-abs_max, vcenter=0, vmax=abs_max)

    with thesis_style():
        fig, ax = plt.subplots(figsize=(13, 5))
        im = ax.imshow(vals, cmap="RdYlGn", norm=norm, aspect="auto")

        ax.set_xticks(range(12))
        ax.set_xticklabels(MONTH_LABELS)
        ax.set_yticks(range(len(regions)))
        ax.set_yticklabels([rshort(r) for r in regions])

        for i in range(len(regions)):
            for j in range(12):
                v = vals[i, j]
                if not np.isnan(v):
                    ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                            fontsize=8,
                            color="white" if abs(v) > abs_max * 0.6 else "black")

        plt.colorbar(im, ax=ax, label="Mean Savings (%)", fraction=0.03, pad=0.02)
        fig.suptitle("Monthly Scheduling Savings by Archetype\n"
                     "Best practical heuristic; red = backfire", fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_monthly_heatmap")


def plot_monthly_lines(monthly_agg):
    print("\n── Fig: Monthly savings lines ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(11, 5))

        for region in CH3_REGIONS:
            rd = monthly_agg[monthly_agg["region"] == region].sort_values("month")
            if len(rd) == 0:
                continue
            ax.plot(rd["month"], rd["mean_savings"],
                    color=rcolor(region), linewidth=2,
                    marker="o", markersize=5, label=rshort(region))
            ax.fill_between(rd["month"], rd["ci_lo"], rd["ci_hi"],
                            color=rcolor(region), alpha=0.10)

        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTH_LABELS)
        ax.set_xlabel("Month")
        ax.set_ylabel("Mean Savings vs. Baseline (%)")
        ax.legend(fontsize=9)
        fig.suptitle("Monthly Scheduling Savings by Archetype\n95% CI shaded",
                     fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_monthly_lines")


def main(recompute=False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Monthly Savings Consistency")
    print("="*60)

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)
    daily_df   = compute_monthly_savings(df_5min, thresholds, recompute)
    monthly    = aggregate_monthly(daily_df)

    # Backfire months
    backfire = monthly[monthly["is_backfire"]]
    if len(backfire) > 0:
        print("\nBackfire months (mean savings < 0):")
        print(backfire[["region_short", "month_label", "mean_savings"]].to_string(index=False))

    # Best/worst 3 months per region
    for region in CH3_REGIONS:
        rd = monthly[monthly["region"] == region].sort_values("mean_savings")
        if len(rd) == 0:
            continue
        worst3 = rd.head(3)["month_label"].tolist()
        best3  = rd.tail(3)["month_label"].tolist()
        print(f"  {rshort(region):10s}  best: {best3}  worst: {worst3}")

    # Pivot for table
    pivot = monthly.pivot(index="region_short", columns="month_label",
                          values="mean_savings")[MONTH_LABELS]

    save_table(pivot.round(1).reset_index(), "table_supp_monthly_savings",
               caption=(
                   "Mean monthly scheduling savings (%) by archetype. "
                   "Best practical heuristic (max of seasonal TOD and traffic light). "
                   "Negative values indicate backfire months."
               ))

    plot_heatmap(monthly)
    plot_monthly_lines(monthly)

    sec = "Supp: Monthly Savings"
    for region in CH3_REGIONS:
        rd = monthly[monthly["region"] == region]
        if len(rd) == 0:
            continue
        record_number(sec, f"{rshort(region)} best month savings",
                      rd["mean_savings"].max(), ".1f")
        record_number(sec, f"{rshort(region)} worst month savings",
                      rd["mean_savings"].min(), ".1f")
    export_numbers()
    print("\n✅ ch3_supp_monthly_savings complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
