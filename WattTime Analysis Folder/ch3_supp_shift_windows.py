"""
ch3_supp_shift_windows.py — Expanded shift window analysis (Section 2.2).

Evaluates scheduling opportunity across five shift structures including
a night shift that crosses midnight.

Outputs (ch3supp/):
    Tables:
        table_supp_shift_summary.csv / .md
        table_supp_shift_flexibility.csv / .md
    Figures:
        fig_supp_shift_grouped_bar.png / .pdf
        fig_supp_shift_flexibility.png / .pdf
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
SHIFTS = {
    "Day":          (6,  18),
    "Evening":      (14, 22),
    "Night":        (22, 6),    # crosses midnight
    "Extended Day": (6,  22),
    "24h Flex":     (0,  24),
}
SHIFT_COLORS = {
    "Day":          "#0077BB",
    "Evening":      "#EE7733",
    "Night":        "#AA3377",
    "Extended Day": "#009988",
    "24h Flex":     "#555555",
}
CACHE_VERSION = 2

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
# SHIFT WINDOW PRE-FILTER (vectorized, called once per region per shift)
# =============================================================================

def prepare_shift_data(df_5min_region: pd.DataFrame,
                       start_h: int, end_h: int) -> pd.DataFrame:
    """
    Return a DataFrame with one row per (shift_date, interval) for the given
    shift window. For night shift, shift_date is the date the shift starts on.

    All normal shifts: filter by hour and use the existing date column.
    Night shift: tag intervals with the previous calendar date so they group
                 together with the preceding 22:00–00:00 block.
    """
    df = df_5min_region.copy()

    if end_h > start_h or end_h == 24:
        # Normal or 24h shift
        if end_h == 24:
            mask = df["hour"] >= start_h
        else:
            mask = (df["hour"] >= start_h) & (df["hour"] < end_h)
        df = df[mask].copy()
        df["shift_date"] = df["date"]
    else:
        # Night shift: hours [start_h, 24) belong to current date;
        # hours [0, end_h) belong to the PREVIOUS calendar date.
        evening = df[df["hour"] >= start_h].copy()
        evening["shift_date"] = evening["date"]

        morning = df[df["hour"] < end_h].copy()
        morning["shift_date"] = morning["date"] - pd.Timedelta(days=1)

        df = pd.concat([evening, morning], ignore_index=True)

    return df.sort_values(["shift_date", "point_time_local"])


def compute_best_hours(shift_df: pd.DataFrame,
                       start_h: int, end_h: int,
                       job_intervals: int) -> dict:
    """
    Compute annual best start hour and seasonal best start hours for this shift.
    Works on hour-aligned starts only.

    Returns: {
        "annual": best_hour_index (position within shift, not clock hour),
        "seasonal": {season: best_hour_index}
    }

    We work in interval-index space (0, 12, 24, ...) rather than clock hours
    to handle night shifts cleanly.
    """
    # Build a profile: for each start-interval-index i, mean MOER across
    # all day's rolling windows starting at i.
    # Vectorized: for each shift_date group, compute rolling window means,
    # then accumulate by start index.

    idx_totals = {}
    idx_counts = {}
    seasonal   = {}

    for shift_date, ddf in shift_df.groupby("shift_date"):
        vals = ddf["value"].values
        n    = len(vals)
        if n < job_intervals:
            continue
        n_win = n - job_intervals + 1
        cs    = np.concatenate([[0], np.cumsum(vals)])
        wm    = (cs[job_intervals:] - cs[:n_win]) / job_intervals

        for i, w in enumerate(wm):
            # Only consider hour-aligned starts (every 12 intervals = 1 hour)
            if i % INTERVALS_PER_HOUR == 0:
                idx_totals[i] = idx_totals.get(i, 0.0) + w
                idx_counts[i] = idx_counts.get(i, 0) + 1

        # Seasonal accumulation
        season = ddf["season"].iloc[0] if "season" in ddf.columns else "unknown"
        if season not in seasonal:
            seasonal[season] = {}
        for i, w in enumerate(wm):
            if i % INTERVALS_PER_HOUR == 0:
                seasonal[season][i] = seasonal[season].get(i, 0.0) + w

    if not idx_totals:
        return {"annual": 0, "seasonal": {}}

    annual_means = {i: idx_totals[i] / idx_counts[i] for i in idx_totals}
    annual_best  = min(annual_means, key=annual_means.get)

    seasonal_best = {}
    for season, s_totals in seasonal.items():
        seasonal_best[season] = min(s_totals, key=s_totals.get)

    return {"annual": annual_best, "seasonal": seasonal_best}


# =============================================================================
# MAIN SIMULATION (vectorized groupby, no per-date DataFrame filters)
# =============================================================================

def run_shift_sim(df_5min: pd.DataFrame, thresholds: pd.DataFrame,
                  shift_name: str, start_h: int, end_h: int,
                  recompute: bool = False) -> pd.DataFrame:

    cache_tag    = f"supp_shift_v2_{shift_name.replace(' ', '_')}"
    cache_params = {"v": CACHE_VERSION}
    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    results = []

    for region in CH3_REGIONS:
        gt, rt = td.get(region, (np.inf, np.inf))
        rd = df_5min[df_5min["region"] == region].copy()
        rd["date"] = pd.to_datetime(rd["date"])

        # Pre-filter to shift window — done ONCE per region per shift
        shift_df = prepare_shift_data(rd, start_h, end_h)
        if len(shift_df) == 0:
            continue

        # Best hours — computed ONCE per region per shift
        bh = compute_best_hours(shift_df, start_h, end_h, job_intervals)
        annual_best_idx = bh["annual"]
        seasonal_best   = bh["seasonal"]

        # Single groupby pass — no repeated DataFrame filters
        for shift_date, ddf in shift_df.groupby("shift_date"):
            vals = ddf["value"].values
            if len(vals) < job_intervals:
                continue

            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None or sim["baseline_moer"] <= 0:
                continue

            baseline = sim["baseline_moer"]
            optimal  = sim["optimal_moer"]

            # Annual TOD: use precomputed best start index
            if annual_best_idx + job_intervals <= len(vals):
                tod_moer = float(np.mean(vals[annual_best_idx:
                                              annual_best_idx + job_intervals]))
            else:
                tod_moer = baseline

            # Seasonal TOD
            season = ddf["season"].iloc[0] if "season" in ddf.columns else "unknown"
            s_idx  = seasonal_best.get(season, annual_best_idx)
            if s_idx + job_intervals <= len(vals):
                stod_moer = float(np.mean(vals[s_idx: s_idx + job_intervals]))
            else:
                stod_moer = baseline

            tl_moer = sim["tl_first_green_moer"]

            def sv(m): return (baseline - m) / baseline * 100

            results.append({
                "region":          region,
                "region_short":    rshort(region),
                "shift":           shift_name,
                "date":            shift_date,
                "season":          season,
                "baseline_moer":   baseline,
                "optimal_moer":    optimal,
                "savings_optimal": sv(optimal),
                "savings_tod":     sv(tod_moer),
                "savings_stod":    sv(stod_moer),
                "savings_tl":      sv(tl_moer),
            })

        n = len([r for r in results if r["region"] == region
                 and r["shift"] == shift_name])
        print(f"    {rshort(region):10s}  {n:,} shift-days")

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, cache_params)
    return df


# =============================================================================
# AGGREGATION
# =============================================================================

def aggregate_shifts(all_sim: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for region in CH3_REGIONS:
        for shift in SHIFTS:
            sub = all_sim[(all_sim["region"] == region) &
                          (all_sim["shift"] == shift)]
            if len(sub) < 10:
                continue
            opt  = sub["savings_optimal"].values
            stod = sub["savings_stod"].values
            tl   = sub["savings_tl"].values
            best_practical = np.maximum(stod, tl)
            best_method    = "Seasonal TOD" if np.mean(stod) >= np.mean(tl) \
                             else "Traffic Light"
            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "shift":        shift,
                "optimal_pct":  round(float(np.mean(opt)),  1),
                "best_method":  best_method,
                "best_pct":     round(float(np.mean(best_practical)), 1),
                "n_days":       len(sub),
            })
    return pd.DataFrame(rows)


def compute_flexibility_premium(agg: pd.DataFrame) -> pd.DataFrame:
    shift_widths = {
        "Day": 12, "Evening": 8, "Night": 8,
        "Extended Day": 16, "24h Flex": 24,
    }
    rows = []
    for region in CH3_REGIONS:
        rd = agg[agg["region"] == region]
        for _, row in rd.iterrows():
            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "shift":        row["shift"],
                "shift_width":  shift_widths[row["shift"]],
                "optimal_pct":  row["optimal_pct"],
            })
    return pd.DataFrame(rows).sort_values(["region", "shift_width"])


# =============================================================================
# FIGURES
# =============================================================================

def plot_grouped_bar(agg: pd.DataFrame):
    print("\n── Fig: Shift window grouped bar ──")
    regions  = list(CH3_REGIONS.keys())
    x        = np.arange(len(regions))
    n_shifts = len(SHIFTS)
    w        = 0.15
    offsets  = np.linspace(-(n_shifts - 1) / 2,
                            (n_shifts - 1) / 2, n_shifts) * w

    with thesis_style():
        fig, ax = plt.subplots(figsize=(13, 6))
        for i, shift in enumerate(SHIFTS):
            sub  = (agg[agg["shift"] == shift]
                    .set_index("region").reindex(regions))
            vals = sub["optimal_pct"].values
            ax.bar(x + offsets[i], vals, w,
                   color=SHIFT_COLORS[shift], alpha=0.85, label=shift)

        ax.axhline(0, color="black", linewidth=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], rotation=30, ha="right")
        ax.set_ylabel("Optimal Savings vs. Baseline (%)")
        ax.legend(fontsize=9)
        fig.suptitle("Optimal Scheduling Savings by Shift Window and Archetype",
                     fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_shift_grouped_bar")


def plot_flexibility_premium(flex_df: pd.DataFrame):
    print("\n── Fig: Flexibility premium ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(8, 5))
        for region in CH3_REGIONS:
            rd = flex_df[flex_df["region"] == region].sort_values("shift_width")
            if len(rd) == 0:
                continue
            ax.plot(rd["shift_width"], rd["optimal_pct"],
                    color=rcolor(region), marker=rmarker(region),
                    markersize=7, linewidth=2, label=rshort(region))

        ax.set_xlabel("Shift Window Width (hours)")
        ax.set_ylabel("Optimal Savings vs. Baseline (%)")
        ax.legend(fontsize=9)
        fig.suptitle("Scheduling Opportunity vs. Shift Width", fontsize=11)
        fig.tight_layout()
        save_fig(fig, "fig_supp_shift_flexibility")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Expanded Shift Window Analysis")
    print("="*60)

    df_5min    = load_5min()
    thresholds = compute_thresholds(df_5min)

    all_frames = []
    for shift_name, (start_h, end_h) in SHIFTS.items():
        print(f"\n  Shift: {shift_name} ({start_h:02d}:00–{end_h:02d}:00)")
        sim = run_shift_sim(df_5min, thresholds, shift_name,
                            start_h, end_h, recompute=recompute)
        print(f"    Total: {len(sim):,} region-days")
        all_frames.append(sim)

    all_sim = pd.concat(all_frames, ignore_index=True)
    agg     = aggregate_shifts(all_sim)
    flex_df = compute_flexibility_premium(agg)

    print("\n" + agg.to_string(index=False))

    save_table(agg, "table_supp_shift_summary",
               caption=(
                   "Optimal and best-practical scheduling savings by shift window "
                   "and archetype. Optimal = perfect oracle. Best practical = max "
                   "of seasonal TOD and traffic light."
               ))
    save_table(flex_df.round(2), "table_supp_shift_flexibility",
               caption="Optimal savings vs. shift width (hours of scheduling flexibility).")

    plot_grouped_bar(agg)
    plot_flexibility_premium(flex_df)

    sec = "Supp: Shift Windows"
    for _, row in agg.iterrows():
        record_number(sec, f"{row['region_short']} {row['shift']} optimal",
                      row["optimal_pct"], ".1f")
    export_numbers()
    print("\n✅ ch3_supp_shift_windows complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)