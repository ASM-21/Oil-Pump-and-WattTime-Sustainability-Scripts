"""
ch3_extended_signal_predictability.py — Why should we expect simple scheduling rules to work?

Quantifies how much of MOER variance is explained by calendar features,
how much scheduling savings each information tier captures, and how long
green windows persist (operator decision window).

Research question:
    "How much of the scheduling opportunity can you capture from calendar
    information alone — and what's the operator's decision window when
    conditions are favorable?"

Outputs:
    Figures:
        fig_ext_savings_staircase.png/pdf  — Savings by information tier
        fig_ext_green_persistence.png/pdf  — P(job completes in green)
        fig_ext_variance_decomposition.png/pdf — % variance by factor
        fig_ext_day_type_distribution.png/pdf — High vs low opportunity days
    Tables:
        table_ext_predictability.csv/md
        table_ext_green_persistence.csv/md

Usage:
    python ch3_extended_signal_predictability.py
    python ch3_extended_signal_predictability.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as sp_stats

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, load_hourly,
    run_scheduling_sim, compute_thresholds, simulate_day,
    CH3_REGIONS, REGION_COLORS, SEASON_ORDER, SEASON_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, TABLES_DIR, save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ FIGURE CONFIG ▼▼▼
# =============================================================================

FIG_STAIRCASE = {
    "figsize": (10, 5),
    "bar_width": 0.13,
    "colors": ["#cccccc", "#f4a582", "#92c5de", "#4393c3", "#2166ac"],
    "tier_labels": ["Random\n(no info)", "Monthly\nbest hour", "Traffic\nlight", "Persistence\n(yesterday)", "Oracle\n(perfect)"],
}

FIG_PERSISTENCE = {
    "figsize": (9, 5),
    "max_lag_intervals": 48,  # 4 hours at 5-min resolution
}

FIG_VARIANCE = {
    "figsize": (9, 5),
    "colors": {"month": "#f4a582", "hour": "#92c5de", "weekday": "#d1e5f0",
               "hour×month": "#fddbc7", "residual": "#eeeeee"},
}

FIG_DAYTYPE = {
    "figsize": (10, 5),
}


# =============================================================================
# ANALYSIS 1 — SAVINGS CEILING BY INFORMATION TIER
# =============================================================================

def compute_savings_by_tier(df_5min, thresholds, recompute=False):
    """
    Compute scheduling savings under different information tiers:
    Tier 0: Random start (baseline)
    Tier 1: Monthly best hour (fixed schedule per month)
    Tier 2: Traffic light heuristic (current approach)
    Tier 3: Persistence (yesterday's green hours as today's forecast)
    Tier 4: Oracle (perfect information)
    """
    print("\n── Savings ceiling by information tier ──")

    cache_tag = "ext_savings_tiers"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    thresh_dict = {
        r["region"]: (r["green_threshold"], r["red_threshold"])
        for _, r in thresholds.iterrows()
    }
    tl_key = f"tl_{TL_STRATEGY}_moer"

    results = []
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        gt, rt = thresh_dict[region]
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")

        # --- Tier 1 prep: monthly best hour ---
        monthly_best_hour = {}
        for month in range(1, 13):
            md = rd[rd["month"] == month]
            if len(md) == 0:
                continue
            hourly_mean = md.groupby("hour")["value"].mean()
            monthly_best_hour[month] = int(hourly_mean.idxmin())

        # --- Per-day simulation ---
        dates = sorted(rd["date"].unique())
        prev_day_green_hours = None

        for date in dates:
            day_df = rd[rd["date"] == date].sort_values("point_time_local")
            vals = day_df["value"].values
            if len(vals) < job_intervals:
                continue

            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None:
                continue

            baseline = sim["baseline_moer"]
            optimal = sim["optimal_moer"]
            tl_moer = sim[tl_key]
            month = day_df["month"].iloc[0]

            if baseline <= 0:
                continue

            # Tier 1: start at monthly best hour
            best_hr = monthly_best_hour.get(month)
            if best_hr is not None:
                hr_offset = best_hr - DAY_SHIFT_START
                start_idx = hr_offset * INTERVALS_PER_HOUR
                end_idx = start_idx + job_intervals
                if 0 <= start_idx and end_idx <= len(vals):
                    tier1_moer = float(np.mean(vals[start_idx:end_idx]))
                else:
                    tier1_moer = baseline
            else:
                tier1_moer = baseline

            # Tier 3: persistence — use yesterday's best window
            if prev_day_green_hours is not None and len(prev_day_green_hours) > 0:
                # Find the hour from yesterday's green set that exists today
                best_persist = None
                for hr in sorted(prev_day_green_hours):
                    hr_off = hr - DAY_SHIFT_START
                    si = hr_off * INTERVALS_PER_HOUR
                    ei = si + job_intervals
                    if 0 <= si and ei <= len(vals):
                        cand = float(np.mean(vals[si:ei]))
                        if best_persist is None or cand < best_persist:
                            best_persist = cand
                tier3_moer = best_persist if best_persist is not None else tl_moer
            else:
                tier3_moer = tl_moer  # fallback to TL on first day

            # Track today's green hours for tomorrow's persistence
            green_mask = vals <= gt
            green_hours_today = set()
            for i, g in enumerate(green_mask):
                if g:
                    green_hours_today.add(DAY_SHIFT_START + i // INTERVALS_PER_HOUR)
            prev_day_green_hours = green_hours_today

            # Savings vs baseline
            sav_t1 = (baseline - tier1_moer) / baseline * 100
            sav_t2 = (baseline - tl_moer) / baseline * 100
            sav_t3 = (baseline - tier3_moer) / baseline * 100
            sav_t4 = (baseline - optimal) / baseline * 100

            results.append({
                "region": region, "date": date, "month": month,
                "season": day_df["season"].iloc[0],
                "baseline_moer": baseline, "optimal_moer": optimal,
                "tier1_moer": tier1_moer, "tier2_moer": tl_moer,
                "tier3_moer": tier3_moer,
                "savings_tier0_pct": 0.0,
                "savings_tier1_pct": sav_t1,
                "savings_tier2_pct": sav_t2,
                "savings_tier3_pct": sav_t3,
                "savings_tier4_pct": sav_t4,
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, {"v": 2})
    print(f"  ✅ Computed {len(df):,} region-days across tiers")
    return df


def plot_savings_staircase(tier_df):
    """Bar chart: savings by information tier, grouped by region."""
    print("\n── Fig: Savings staircase ──")
    cfg = FIG_STAIRCASE

    summary = tier_df.groupby("region").agg({
        "savings_tier0_pct": "mean",
        "savings_tier1_pct": "mean",
        "savings_tier2_pct": "mean",
        "savings_tier3_pct": "mean",
        "savings_tier4_pct": "mean",
    }).reindex(CH3_REGIONS.keys())

    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        regions = list(summary.index)
        x = np.arange(len(regions))
        w = cfg["bar_width"]
        tiers = ["savings_tier0_pct", "savings_tier1_pct", "savings_tier2_pct",
                 "savings_tier3_pct", "savings_tier4_pct"]

        for i, (tier, label, color) in enumerate(zip(tiers, cfg["tier_labels"], cfg["colors"])):
            vals = summary[tier].values
            ax.bar(x + i * w, vals, w, label=label, color=color, edgecolor="white", linewidth=0.5)

        ax.set_xticks(x + 2 * w)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("Mean Scheduling Savings (%)")
        ax.legend(fontsize=8, ncol=5, loc="upper left")
        ax.set_ylim(bottom=0)

        save_fig(fig, "fig_ext_savings_staircase")

    # Record numbers
    for region in CH3_REGIONS:
        row = summary.loc[region]
        t2 = row["savings_tier2_pct"]
        t4 = row["savings_tier4_pct"]
        capture = t2 / t4 * 100 if t4 > 0 else 100
        record_number("Predictability", f"{rshort(region)} TL captures % of oracle", capture, ".0f")

    overall_t2 = summary["savings_tier2_pct"].mean()
    overall_t4 = summary["savings_tier4_pct"].mean()
    record_number("Predictability", "Overall TL capture of oracle %", overall_t2 / overall_t4 * 100, ".0f")
    record_number("Predictability", "Overall persistence capture of oracle %",
                  summary["savings_tier3_pct"].mean() / overall_t4 * 100, ".0f")


# =============================================================================
# ANALYSIS 2 — GREEN PERSISTENCE & JOB COMPLETION
# =============================================================================

def compute_green_persistence(df_5min, thresholds):
    """
    P(still green at t+k | green at t) within operating window.
    Also: fraction of a 2hr job that remains green if started at green.
    """
    print("\n── Green persistence analysis ──")
    max_lag = FIG_PERSISTENCE["max_lag_intervals"]
    thresh_dict = {
        r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()
    }

    persistence_rows = []
    job_completion_rows = []
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)

    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        gt = thresh_dict[region]
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].sort_values("point_time_local")

        green_mask = (rd["value"].values <= gt).astype(int)

        # Persistence: P(green at t+k | green at t)
        green_indices = np.where(green_mask == 1)[0]
        if len(green_indices) < 100:
            continue

        for lag in range(0, max_lag + 1):
            valid = green_indices[green_indices + lag < len(green_mask)]
            if len(valid) == 0:
                continue
            still_green = green_mask[valid + lag].sum()
            p = still_green / len(valid)
            persistence_rows.append({
                "region": region, "lag_intervals": lag,
                "lag_minutes": lag * 5,
                "p_still_green": p,
            })

        # Job completion in green: start at green, what fraction stays green?
        for gi in green_indices:
            end = gi + job_intervals
            if end > len(green_mask):
                break
            job_window = green_mask[gi:end]
            frac_green = job_window.sum() / job_intervals
            job_completion_rows.append({
                "region": region, "frac_green": frac_green,
            })

    persist_df = pd.DataFrame(persistence_rows)
    job_df = pd.DataFrame(job_completion_rows)

    # Summary stats
    for region in CH3_REGIONS:
        rd = persist_df[persist_df["region"] == region]
        if len(rd) == 0:
            continue
        # Find lag where P drops below 0.5
        below_50 = rd[rd["p_still_green"] < 0.5]
        if len(below_50) > 0:
            half_life_min = below_50["lag_minutes"].iloc[0]
        else:
            half_life_min = rd["lag_minutes"].max()
        record_number("Predictability", f"{rshort(region)} green half-life (min)", half_life_min, ".0f")

        jd = job_df[job_df["region"] == region]
        if len(jd) > 0:
            mean_frac = jd["frac_green"].mean()
            record_number("Predictability", f"{rshort(region)} job-in-green fraction", mean_frac, ".2f")

    return persist_df, job_df


def plot_green_persistence(persist_df, job_df):
    """Plot persistence curves and job-completion-in-green bars."""
    print("\n── Fig: Green persistence ──")
    cfg = FIG_PERSISTENCE

    with thesis_style():
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

        # Left: persistence curves
        for region in CH3_REGIONS:
            rd = persist_df[persist_df["region"] == region].sort_values("lag_minutes")
            if len(rd) == 0:
                continue
            ax1.plot(rd["lag_minutes"], rd["p_still_green"],
                     color=rcolor(region), linewidth=1.8, label=rshort(region))

        ax1.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
        ax1.set_xlabel("Time Elapsed (minutes)")
        ax1.set_ylabel("P(still green)")
        ax1.set_title("Green Window Persistence")
        ax1.legend(fontsize=8)
        ax1.set_ylim(0, 1.05)

        # Right: job completion in green
        regions = list(CH3_REGIONS.keys())
        means = []
        for region in regions:
            jd = job_df[job_df["region"] == region]
            means.append(jd["frac_green"].mean() * 100 if len(jd) > 0 else 0)

        bars = ax2.bar(range(len(regions)), means,
                       color=[rcolor(r) for r in regions], edgecolor="white")
        ax2.set_xticks(range(len(regions)))
        ax2.set_xticklabels([rshort(r) for r in regions], fontsize=9)
        ax2.set_ylabel(f"% of {REFERENCE_JOB_HOURS}hr Job in Green")
        ax2.set_title("Job Completion in Green\n(started at green interval)")
        ax2.set_ylim(0, 105)

        for bar, val in zip(bars, means):
            ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                     f"{val:.0f}%", ha="center", va="bottom", fontsize=9)

        plt.tight_layout()
        save_fig(fig, "fig_ext_green_persistence")


# =============================================================================
# ANALYSIS 3 — VARIANCE DECOMPOSITION
# =============================================================================

def compute_variance_decomposition(df_5min):
    """
    Stepwise R² from calendar features:
    Step 1: month only
    Step 2: + hour
    Step 3: + weekday
    Step 4: + hour×month interaction
    Residual = what only real-time data captures.
    """
    print("\n── Variance decomposition ──")

    rows = []
    for region in CH3_REGIONS:
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ].copy()
        if len(rd) < 1000:
            continue

        y = rd["value"].values
        ss_total = np.sum((y - y.mean()) ** 2)

        # Step 1: month only
        month_means = rd.groupby("month")["value"].transform("mean").values
        ss_month = np.sum((month_means - y.mean()) ** 2)
        r2_month = ss_month / ss_total

        # Step 2: month + hour
        mh_means = rd.groupby(["month", "hour"])["value"].transform("mean").values
        ss_mh = np.sum((mh_means - y.mean()) ** 2)
        r2_month_hour = ss_mh / ss_total

        # Step 3: month + hour + weekday
        rd["is_wkday"] = (~rd["is_weekend"]).astype(int)
        mhw_means = rd.groupby(["month", "hour", "is_wkday"])["value"].transform("mean").values
        ss_mhw = np.sum((mhw_means - y.mean()) ** 2)
        r2_mhw = ss_mhw / ss_total

        # Step 4: month × hour interaction (same as step 2 since we already group by both)
        # Use finer: season × hour × weekday
        rd["_grp"] = rd["season"].astype(str) + "_" + rd["hour"].astype(str) + "_" + rd["is_wkday"].astype(str)
        grp_means = rd.groupby("_grp")["value"].transform("mean").values
        ss_grp = np.sum((grp_means - y.mean()) ** 2)
        r2_full = ss_grp / ss_total

        rows.append({
            "region": region,
            "r2_month": r2_month,
            "r2_month_hour": r2_month_hour,
            "r2_month_hour_weekday": r2_mhw,
            "r2_full_calendar": r2_full,
            "r2_residual": 1 - r2_full,
            # Incremental contributions
            "incr_month": r2_month,
            "incr_hour": r2_month_hour - r2_month,
            "incr_weekday": r2_mhw - r2_month_hour,
            "incr_interaction": r2_full - r2_mhw,
        })
        record_number("Predictability", f"{rshort(region)} R² calendar full", r2_full, ".3f")
        record_number("Predictability", f"{rshort(region)} R² hour alone adds", r2_month_hour - r2_month, ".3f")

    return pd.DataFrame(rows)


def plot_variance_decomposition(var_df):
    """Stacked bar: % variance explained by each factor, by region."""
    print("\n── Fig: Variance decomposition ──")
    cfg = FIG_VARIANCE

    with thesis_style():
        fig, ax = plt.subplots(figsize=cfg["figsize"])
        regions = list(CH3_REGIONS.keys())
        var_df = var_df.set_index("region").reindex(regions)

        components = ["incr_month", "incr_hour", "incr_weekday", "incr_interaction"]
        labels = ["Month/Season", "Hour of Day", "Weekday/Weekend", "Interactions"]
        colors = [cfg["colors"]["month"], cfg["colors"]["hour"],
                  cfg["colors"]["weekday"], cfg["colors"]["hour×month"]]

        x = np.arange(len(regions))
        bottom = np.zeros(len(regions))

        for comp, label, color in zip(components, labels, colors):
            vals = var_df[comp].values * 100
            ax.bar(x, vals, bottom=bottom, label=label, color=color, edgecolor="white", linewidth=0.5)
            bottom += vals

        # Residual
        residual = var_df["r2_residual"].values * 100
        ax.bar(x, residual, bottom=bottom, label="Residual (unpredictable)",
               color=cfg["colors"]["residual"], edgecolor="white", linewidth=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("% of MOER Variance")
        ax.set_ylim(0, 105)
        ax.legend(fontsize=8, loc="upper right")

        # Annotate total calendar R²
        for i, region in enumerate(regions):
            r2 = var_df.loc[region, "r2_full_calendar"] * 100
            ax.text(i, r2 + 2, f"{r2:.0f}%", ha="center", fontsize=8, fontweight="bold")

        save_fig(fig, "fig_ext_variance_decomposition")


# =============================================================================
# ANALYSIS 4 — DAY-TYPE CLASSIFICATION
# =============================================================================

def classify_day_types(df_5min, thresholds):
    """
    Classify each day as high-opportunity or low-opportunity based on
    intra-day MOER IQR relative to regional median.
    """
    print("\n── Day-type classification ──")

    rows = []
    for region in CH3_REGIONS:
        rd = df_5min[
            (df_5min["region"] == region)
            & (df_5min["hour"] >= DAY_SHIFT_START)
            & (df_5min["hour"] < DAY_SHIFT_END)
        ]
        daily_iqr = rd.groupby("date")["value"].apply(lambda x: x.quantile(0.75) - x.quantile(0.25))
        median_iqr = daily_iqr.median()

        for date, iqr_val in daily_iqr.items():
            day_data = rd[rd["date"] == date]
            if len(day_data) == 0:
                continue
            rows.append({
                "region": region,
                "date": date,
                "season": day_data["season"].iloc[0],
                "daily_iqr": iqr_val,
                "is_high_opportunity": iqr_val > median_iqr,
                "median_iqr": median_iqr,
            })

    df = pd.DataFrame(rows)

    # Stats
    for region in CH3_REGIONS:
        rd = df[df["region"] == region]
        pct_high = rd["is_high_opportunity"].mean() * 100
        record_number("Predictability", f"{rshort(region)} % high-opportunity days", pct_high, ".0f")

    return df


def plot_day_types(daytype_df):
    """Stacked bar: % high vs low opportunity days by region × season."""
    print("\n── Fig: Day-type distribution ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=FIG_DAYTYPE["figsize"])
        regions = list(CH3_REGIONS.keys())
        seasons = SEASON_ORDER
        n_r = len(regions)
        n_s = len(seasons)
        width = 0.18
        x = np.arange(n_r)

        for j, season in enumerate(seasons):
            pcts = []
            for region in regions:
                rd = daytype_df[(daytype_df["region"] == region) & (daytype_df["season"] == season)]
                pcts.append(rd["is_high_opportunity"].mean() * 100 if len(rd) > 0 else 0)
            ax.bar(x + j * width, pcts, width, label=season.capitalize(),
                   color=SEASON_COLORS[season], edgecolor="white", linewidth=0.5)

        ax.set_xticks(x + 1.5 * width)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel("% High-Opportunity Days")
        ax.axhline(50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.legend(fontsize=9)
        ax.set_ylim(0, 100)

        save_fig(fig, "fig_ext_day_type_distribution")


# =============================================================================
# BUILD SUMMARY TABLE
# =============================================================================

def build_predictability_table(tier_df, var_df, persist_df, job_df):
    """Combine all predictability metrics into one summary table."""
    print("\n── Building predictability summary table ──")

    rows = []
    for region in CH3_REGIONS:
        r = {"region": region, "archetype": CH3_REGIONS[region]["archetype"]}

        # Tier savings
        td = tier_df[tier_df["region"] == region]
        if len(td) > 0:
            r["savings_monthly_pct"] = td["savings_tier1_pct"].mean()
            r["savings_tl_pct"] = td["savings_tier2_pct"].mean()
            r["savings_persistence_pct"] = td["savings_tier3_pct"].mean()
            r["savings_oracle_pct"] = td["savings_tier4_pct"].mean()
            r["tl_capture_of_oracle_pct"] = (
                r["savings_tl_pct"] / r["savings_oracle_pct"] * 100
                if r["savings_oracle_pct"] > 0 else 100
            )

        # Variance
        vr = var_df[var_df["region"] == region]
        if len(vr) > 0:
            r["r2_calendar"] = vr["r2_full_calendar"].values[0]

        # Persistence
        pr = persist_df[persist_df["region"] == region]
        if len(pr) > 0:
            below_50 = pr[pr["p_still_green"] < 0.5]
            r["green_half_life_min"] = below_50["lag_minutes"].iloc[0] if len(below_50) > 0 else pr["lag_minutes"].max()

        # Job completion
        jd = job_df[job_df["region"] == region]
        if len(jd) > 0:
            r["job_in_green_pct"] = jd["frac_green"].mean() * 100

        rows.append(r)

    table = pd.DataFrame(rows)
    save_table(table, "table_ext_predictability",
               "Signal predictability metrics by grid archetype.")
    return table


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_5min = load_5min()
    thresholds = compute_thresholds(df_5min)

    # Analysis 1: Savings by tier
    tier_df = compute_savings_by_tier(df_5min, thresholds, recompute=recompute)
    plot_savings_staircase(tier_df)

    # Analysis 2: Green persistence
    persist_df, job_df = compute_green_persistence(df_5min, thresholds)
    plot_green_persistence(persist_df, job_df)

    # Analysis 3: Variance decomposition
    var_df = compute_variance_decomposition(df_5min)
    plot_variance_decomposition(var_df)

    # Analysis 4: Day types
    daytype_df = classify_day_types(df_5min, thresholds)
    plot_day_types(daytype_df)

    # Summary table
    build_predictability_table(tier_df, var_df, persist_df, job_df)

    export_numbers()
    print("\n✅ Signal predictability analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
