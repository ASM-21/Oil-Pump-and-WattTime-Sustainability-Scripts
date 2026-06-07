"""
ch3_supp_weekend_weekday.py — Weekend vs. weekday MOER analysis (Section 2.4).

Outputs (ch3supp/):
    Tables:
        table_supp_wkd_summary.csv / .md
    Figures:
        fig_supp_wkd_profiles.png / .pdf

Usage:
    python ch3_supp_weekend_weekday.py
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
    CH3_REGIONS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    rshort, rcolor,
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


def ks_two_sample(x, y, n_perm=1000):
    """
    Kolmogorov-Smirnov two-sample test via permutation (no scipy required).
    Returns approximate p-value.
    """
    x, y = np.array(x), np.array(y)
    combined = np.concatenate([x, y])

    def ks_stat(a, b):
        all_vals = np.sort(np.concatenate([a, b]))
        cdf_a = np.searchsorted(np.sort(a), all_vals, side="right") / len(a)
        cdf_b = np.searchsorted(np.sort(b), all_vals, side="right") / len(b)
        return float(np.max(np.abs(cdf_a - cdf_b)))

    observed = ks_stat(x, y)
    rng = np.random.default_rng(42)
    count = 0
    for _ in range(n_perm):
        perm = rng.permutation(combined)
        if ks_stat(perm[:len(x)], perm[len(x):]) >= observed:
            count += 1
    return observed, count / n_perm


def compute_summary(df_5min, thresholds, recompute=False):
    cache_tag    = "supp_wkd_summary"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    # Tag weekday/weekend
    df = df_5min.copy()
    df["point_time_local"] = pd.to_datetime(df["point_time_local"])
    df["is_weekend"] = df["point_time_local"].dt.dayofweek >= 5

    window = df[
        (df["hour"] >= DAY_SHIFT_START) & (df["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for region in CH3_REGIONS:
        rd  = df[df["region"] == region]
        rw  = window[window["region"] == region]
        gt, rt = td.get(region, (np.inf, np.inf))

        for day_type, is_wkd in [("weekday", False), ("weekend", True)]:
            sub = rd[rd["is_weekend"] == is_wkd]
            sub_win = rw[rw["is_weekend"] == is_wkd]

            if len(sub) == 0:
                continue

            opt_savings = []
            for date, ddf in sub_win.groupby("date"):
                vals = ddf.sort_values("point_time_local")["value"].values
                sim  = simulate_day(vals, job_intervals, gt, rt)
                if sim is None or sim["baseline_moer"] <= 0:
                    continue
                opt_savings.append(
                    (sim["baseline_moer"] - sim["optimal_moer"])
                    / sim["baseline_moer"] * 100
                )

            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "day_type":     day_type,
                "mean_moer":    float(sub["value"].mean()),
                "optimal_pct":  float(np.mean(opt_savings)) if opt_savings else np.nan,
                "n_days":       sub_win.groupby("date").ngroups,
            })

    df_out = pd.DataFrame(rows)

    # Pivot and compute delta + KS test
    final_rows = []
    for region in CH3_REGIONS:
        wkd = df_out[(df_out["region"] == region) & (df_out["day_type"] == "weekday")]
        wkn = df_out[(df_out["region"] == region) & (df_out["day_type"] == "weekend")]
        if len(wkd) == 0 or len(wkn) == 0:
            continue

        rd      = df[df["region"] == region]
        wkd_v   = rd[~(rd.get("is_weekend", False))]["value"].values if "is_weekend" in rd.columns else np.array([])
        wkn_v   = rd[rd.get("is_weekend", False)]["value"].values if "is_weekend" in rd.columns else np.array([])

        ks_d, ks_p = (np.nan, np.nan)
        if len(wkd_v) > 100 and len(wkn_v) > 100:
            # Sample for speed
            rng   = np.random.default_rng(42)
            samp  = min(5000, len(wkd_v), len(wkn_v))
            ks_d, ks_p = ks_two_sample(
                rng.choice(wkd_v, samp, replace=False),
                rng.choice(wkn_v, samp, replace=False),
                n_perm=500
            )

        final_rows.append({
            "region":          region,
            "region_short":    rshort(region),
            "weekday_mean":    round(float(wkd["mean_moer"].values[0]), 1),
            "weekend_mean":    round(float(wkn["mean_moer"].values[0]), 1),
            "delta_moer":      round(float(wkn["mean_moer"].values[0]) -
                                     float(wkd["mean_moer"].values[0]), 1),
            "weekday_opt_pct": round(float(wkd["optimal_pct"].values[0]), 1),
            "weekend_opt_pct": round(float(wkn["optimal_pct"].values[0]), 1),
            "ks_stat":         round(ks_d, 3) if not np.isnan(ks_d) else "",
            "ks_p_value":      round(ks_p, 3) if not np.isnan(ks_p) else "",
        })

    result = pd.DataFrame(final_rows)
    save_cache(result, cache_tag, cache_params)
    return result


def compute_hourly_profiles(df_5min):
    df = df_5min.copy()
    df["point_time_local"] = pd.to_datetime(df["point_time_local"])
    df["is_weekend"] = df["point_time_local"].dt.dayofweek >= 5

    profiles = {}
    for region in CH3_REGIONS:
        rd = df[df["region"] == region]
        profiles[region] = {
            "weekday": rd[~rd["is_weekend"]].groupby("hour")["value"].mean(),
            "weekend": rd[rd["is_weekend"]].groupby("hour")["value"].mean(),
        }
    return profiles


def plot_profiles(profiles):
    print("\n── Fig: Weekday vs weekend profiles ──")
    regions = list(CH3_REGIONS.keys())

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(13, 8), sharey=False)
        axes = axes.flatten()

        for ax, region in zip(axes, regions):
            p   = profiles[region]
            col = rcolor(region)
            h   = range(0, 24)

            wkd = p["weekday"].reindex(h)
            wkn = p["weekend"].reindex(h)

            ax.plot(h, wkd.values, color=col, linewidth=2,
                    linestyle="-", label="Weekday")
            ax.plot(h, wkn.values, color=col, linewidth=2,
                    linestyle="--", label="Weekend", alpha=0.7)
            ax.axvspan(DAY_SHIFT_START, DAY_SHIFT_END,
                       color="grey", alpha=0.08, label="Shift window")
            ax.set_title(rshort(region), fontsize=11)
            ax.set_xlabel("Hour of Day")
            ax.set_ylabel(f"Mean MOER ({SIGNAL_UNIT})")
            ax.set_xlim(0, 23)
            ax.legend(fontsize=8)

        fig.suptitle("Weekday vs. Weekend Mean MOER Profiles by Archetype", fontsize=12)
        fig.tight_layout()
        save_fig(fig, "fig_supp_wkd_profiles")


def main(recompute=False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Weekend vs. Weekday MOER")
    print("="*60)

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)
    summary    = compute_summary(df_5min, thresholds, recompute)
    profiles   = compute_hourly_profiles(df_5min)

    print(summary.to_string(index=False))

    save_table(summary, "table_supp_wkd_summary",
               caption=(
                   "Weekday vs. weekend MOER statistics by archetype. "
                   "KS p-value from permutation test (500 permutations, n=5000 sample)."
               ))

    plot_profiles(profiles)

    sec = "Supp: Weekend vs Weekday"
    for _, row in summary.iterrows():
        record_number(sec, f"{row['region_short']} weekday-weekend delta",
                      row["delta_moer"], "+.1f")
    export_numbers()
    print("\n✅ ch3_supp_weekend_weekday complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
