"""
ch3_supp_temporal_holdout.py — Calibration staleness penalty for scheduling heuristics.

Quantifies how much scheduling performance degrades when heuristic parameters
(thresholds and best hours) are frozen from older data rather than recalibrated
on the full available period.

Three calibration scenarios:
  reference  : parameters from all available years (2022-2024), evaluated on 2022-2024
  stale_1yr  : parameters from 2022 only,          evaluated on 2023-2024
  stale_2yr  : parameters from 2022-2023,           evaluated on 2024

For each scenario, four heuristics are evaluated:
  annual_tod     — start at best hour from calibration data
  seasonal_tod   — start at season-specific best hour from calibration data
  traffic_light  — first-green using thresholds from calibration data
  forecast_proxy — perfect oracle (lowest 2h window); threshold-independent upper bound

Key metric: retention = stale_savings / reference_savings * 100
  100% = no calibration penalty; <100% = degradation from stale parameters.

Outputs:
    Tables:
        table_supp_holdout_summary.csv / .md     (region x method x scenario)
        table_supp_holdout_param_drift.csv / .md (threshold and best-hour drift)
    Figures:
        fig_supp_holdout_retention.png / .pdf    (retention heatmap: region x method)
        fig_supp_holdout_abs_savings.png / .pdf  (absolute savings: ref vs stale bars)
        fig_supp_holdout_param_drift.png / .pdf  (threshold drift per region)

Usage:
    python ch3_supp_temporal_holdout.py
    python ch3_supp_temporal_holdout.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

import ch3_common
from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day, bootstrap_ci,
    CH3_REGIONS, REGION_COLORS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    save_cache, load_cache,
)

# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================
SCENARIOS = {
    "reference": {"calib_years": [2022, 2023, 2024], "eval_years": [2022, 2023, 2024]},
    "stale_1yr": {"calib_years": [2022],              "eval_years": [2023, 2024]},
    "stale_2yr": {"calib_years": [2022, 2023],        "eval_years": [2024]},
}
SCENARIO_LABELS = {
    "reference": "Reference\n(2022–24 params,\n2022–24 eval)",
    "stale_1yr": "Stale 1yr\n(2022 params,\n2023–24 eval)",
    "stale_2yr": "Stale 2yr\n(2022–23 params,\n2024 eval)",
}
METHODS = ["annual_tod", "seasonal_tod", "traffic_light", "forecast_proxy"]
METHOD_LABELS = {
    "annual_tod":     "Annual TOD",
    "seasonal_tod":   "Seasonal TOD",
    "traffic_light":  f"Traffic Light",
    "forecast_proxy": "Forecast",
}
METHOD_COLORS = {
    "annual_tod":     "#0077BB",
    "seasonal_tod":   "#EE7733",
    "traffic_light":  "#2ca02c",
    "forecast_proxy": "#AA3377",
}

CACHE_VERSION = 3

# Output paths — all supp scripts write here, not to ch3_outputs/
SUPP_DIR     = Path(__file__).parent / "ch3supp"
SUPP_FIGURES = SUPP_DIR / "figures"
SUPP_TABLES  = SUPP_DIR / "tables"
SUPP_NUMBERS = SUPP_DIR / "ch3_supp_numbers.md"
# ▲▲▲ END CONFIG ▲▲▲

# Redirect ch3_common I/O to the supp folder.
# Must happen before any save_fig / save_table / export_numbers calls.
ch3_common.FIGURES_DIR  = SUPP_FIGURES
ch3_common.TABLES_DIR   = SUPP_TABLES
ch3_common.NUMBERS_FILE = SUPP_NUMBERS
SUPP_FIGURES.mkdir(parents=True, exist_ok=True)
SUPP_TABLES.mkdir(parents=True, exist_ok=True)


# =============================================================================
# PARAMETER COMPUTATION
# =============================================================================

def compute_params(df_5min: pd.DataFrame, calib_years: list) -> dict:
    """
    Derive all heuristic parameters from calib_years data.

    Returns dict keyed by region:
        green_threshold, red_threshold,
        annual_best_hour,
        seasonal_best_hours {season: hour}
    """
    train = df_5min[df_5min["year"].isin(calib_years)]
    win   = train[(train["hour"] >= DAY_SHIFT_START) & (train["hour"] < DAY_SHIFT_END)]

    params = {}
    for region in CH3_REGIONS:
        rd = win[win["region"] == region]
        if len(rd) == 0:
            continue

        gt = float(rd["value"].quantile(GREEN_PERCENTILE / 100))
        rt = float(rd["value"].quantile(RED_PERCENTILE / 100))

        hourly_mean = rd.groupby("hour")["value"].mean()
        annual_best = int(hourly_mean.idxmin())

        seasonal_best = {}
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                seasonal_best[season] = annual_best
                continue
            sh_mean = sd.groupby("hour")["value"].mean()
            seasonal_best[season] = int(sh_mean.idxmin())

        params[region] = {
            "green_threshold":     gt,
            "red_threshold":       rt,
            "annual_best_hour":    annual_best,
            "seasonal_best_hours": seasonal_best,
        }
    return params


# =============================================================================
# PER-DAY TOD MOER
# =============================================================================

def tod_moer(day_values: np.ndarray, best_hour: int, job_intervals: int):
    """Mean MOER for a job starting at best_hour within the shift window."""
    idx = (best_hour - DAY_SHIFT_START) * INTERVALS_PER_HOUR
    if idx < 0 or idx + job_intervals > len(day_values):
        return None
    return float(np.mean(day_values[idx: idx + job_intervals]))


# =============================================================================
# SIMULATION
# =============================================================================

def run_simulation(df_5min: pd.DataFrame, params: dict, eval_years: list,
                   scenario_tag: str, recompute: bool = False) -> pd.DataFrame:
    """
    Evaluate all 4 methods on eval_years using frozen params.
    Returns one row per region-day.
    """
    cache_tag    = f"supp_holdout_{scenario_tag}"
    cache_params = {"eval_years": sorted(eval_years), "v": CACHE_VERSION}

    if not recompute:
        cached = load_cache(cache_tag, cache_params)
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key        = f"tl_{TL_STRATEGY}_moer"

    window = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END) &
        (df_5min["year"].isin(eval_years))
    ]

    results = []
    for region, rp in params.items():
        gt       = rp["green_threshold"]
        rt       = rp["red_threshold"]
        annual_h = rp["annual_best_hour"]
        season_h = rp["seasonal_best_hours"]

        rd = window[window["region"] == region].sort_values("point_time_local")

        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            if len(vals) < job_intervals:
                continue

            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None:
                continue

            baseline = sim["baseline_moer"]
            if baseline <= 0:
                continue

            season     = ddf["season"].iloc[0]
            sh         = season_h.get(season, annual_h)
            m_annual   = tod_moer(vals, annual_h, job_intervals) or baseline
            m_seasonal = tod_moer(vals, sh,       job_intervals) or baseline
            m_tl       = sim[tl_key]
            m_forecast = sim["optimal_moer"]

            def sv(m): return (baseline - m) / baseline * 100

            results.append({
                "region":                 region,
                "date":                   date,
                "year":                   ddf["year"].iloc[0],
                "season":                 season,
                "scenario":               scenario_tag,
                "baseline_moer":          baseline,
                "savings_annual_tod":     sv(m_annual),
                "savings_seasonal_tod":   sv(m_seasonal),
                "savings_traffic_light":  sv(m_tl),
                "savings_forecast_proxy": sv(m_forecast),
            })

    df = pd.DataFrame(results)
    save_cache(df, cache_tag, cache_params)
    print(f"  {scenario_tag:12s}  {len(df):,} region-days across {eval_years}")
    return df


# =============================================================================
# AGGREGATION
# =============================================================================

def aggregate_by_region_method(sim_df: pd.DataFrame) -> pd.DataFrame:
    """Mean savings + 95% bootstrap CI per (region, method) for one scenario."""
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        for method in METHODS:
            col  = f"savings_{method}"
            vals = rd[col].dropna().values
            if len(vals) < 10:
                continue
            mn       = float(np.mean(vals))
            lo, hi   = bootstrap_ci(vals)
            rows.append({
                "region":       region,
                "region_short": rshort(region),
                "method":       method,
                "mean_savings": mn,
                "ci_lo":        lo,
                "ci_hi":        hi,
                "n_days":       len(vals),
            })
    return pd.DataFrame(rows)


def build_summary(scenario_aggs: dict) -> pd.DataFrame:
    """
    Merge reference and stale scenarios into one summary table.
    Adds retention = stale_savings / reference_savings * 100.
    """
    ref = scenario_aggs["reference"].set_index(["region", "method"])

    rows = []
    for scenario, agg in scenario_aggs.items():
        for _, row in agg.iterrows():
            ref_row = ref.loc[(row["region"], row["method"])] if (row["region"], row["method"]) in ref.index else None
            ref_savings = ref_row["mean_savings"] if ref_row is not None else np.nan
            retention   = row["mean_savings"] / ref_savings * 100 if ref_savings and ref_savings > 0 else np.nan
            rows.append({
                "scenario":       scenario,
                "region":         row["region"],
                "region_short":   row["region_short"],
                "method":         row["method"],
                "method_label":   METHOD_LABELS[row["method"]],
                "mean_savings":   row["mean_savings"],
                "ci_lo":          row["ci_lo"],
                "ci_hi":          row["ci_hi"],
                "ref_savings":    ref_savings,
                "retention_pct":  retention,
                "n_days":         row["n_days"],
            })
    return pd.DataFrame(rows)


def build_param_drift(all_params: dict) -> pd.DataFrame:
    """
    Compare parameters across calibration scenarios.
    Shows threshold drift and best-hour shift from reference.
    """
    ref_params = all_params["reference"]
    rows = []
    for scenario, params in all_params.items():
        for region, rp in params.items():
            ref = ref_params.get(region, {})
            rows.append({
                "scenario":           scenario,
                "region":             region,
                "region_short":       rshort(region),
                "green_threshold":    rp["green_threshold"],
                "red_threshold":      rp["red_threshold"],
                "annual_best_hour":   rp["annual_best_hour"],
                "gt_drift":           rp["green_threshold"] - ref.get("green_threshold", np.nan),
                "rt_drift":           rp["red_threshold"]   - ref.get("red_threshold",   np.nan),
                "best_hour_shift":    rp["annual_best_hour"] - ref.get("annual_best_hour", 0),
            })
    return pd.DataFrame(rows)


# =============================================================================
# FIGURES
# =============================================================================

def plot_savings_with_reference(summary: pd.DataFrame):
    """
    One panel per method. For each region:
      - Reference savings shown as a filled circle with 95% CI whisker (the target)
      - Stale 1yr and Stale 2yr shown as bars with CI error bars

    The gap between a bar and its reference marker is the calibration penalty.
    """
    print("\n── Fig: Savings with reference markers ──")
    regions = list(CH3_REGIONS.keys())
    x       = np.arange(len(regions))
    bar_w   = 0.30

    stale_style = {
        "stale_1yr": {"offset": -bar_w / 2, "alpha": 0.75, "hatch": "",
                      "label": "Stale 1yr (2022 params, eval 2023-24)"},
        "stale_2yr": {"offset": +bar_w / 2, "alpha": 0.45, "hatch": "///",
                      "label": "Stale 2yr (2022-23 params, eval 2024)"},
    }

    with thesis_style():
        fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharey=False)
        axes = axes.flatten()

        for ax, method in zip(axes, METHODS):
            color = METHOD_COLORS[method]

            # Draw stale bars first (behind reference markers)
            for scenario, style in stale_style.items():
                sub = (summary[(summary["method"] == method) &
                               (summary["scenario"] == scenario)]
                       .set_index("region").reindex(regions))
                vals = sub["mean_savings"].values
                errs = np.array([
                    vals - sub["ci_lo"].values,
                    sub["ci_hi"].values - vals,
                ])
                errs = np.nan_to_num(errs)
                ax.bar(x + style["offset"], vals, bar_w,
                       color=color, alpha=style["alpha"], hatch=style["hatch"],
                       label=style["label"],
                       yerr=errs, capsize=3, error_kw={"linewidth": 0.8},
                       zorder=2)

            # Reference as markers on top — one per region
            ref = (summary[(summary["method"] == method) &
                           (summary["scenario"] == "reference")]
                   .set_index("region").reindex(regions))
            ref_vals = ref["mean_savings"].values
            ref_lo   = ref["ci_lo"].values
            ref_hi   = ref["ci_hi"].values
            ax.errorbar(x, ref_vals,
                        yerr=[ref_vals - ref_lo, ref_hi - ref_vals],
                        fmt="D", color="black", markersize=6, linewidth=1.2,
                        capsize=4, zorder=5, label="Reference (2022-24 params)")

            ax.axhline(0, color="black", linewidth=0.6)
            ax.set_title(METHOD_LABELS[method], fontsize=11)
            ax.set_xticks(x)
            ax.set_xticklabels([rshort(r) for r in regions], rotation=30, ha="right")
            ax.set_ylabel("Savings vs. Baseline (%)")
            ax.legend(fontsize=8, loc="upper center")

        fig.suptitle(
            "Scheduling Savings Under Stale vs. Full-Period Calibration\n"
            "Diamonds = reference (full 2022-24 parameters); "
            "bars = stale parameters. Gap = calibration penalty.",
            fontsize=11
        )
        fig.tight_layout()
        save_fig(fig, "fig_supp_holdout_savings")


# =============================================================================
# RECORD KEY NUMBERS
# =============================================================================

def record_key_numbers(summary: pd.DataFrame):
    sec = "Supp: Temporal Holdout"
    for scenario in ["stale_1yr", "stale_2yr"]:
        sub = summary[summary["scenario"] == scenario]
        if len(sub) == 0:
            continue
        mean_ret  = sub["retention_pct"].mean()
        min_ret   = sub["retention_pct"].min()
        min_row   = sub.loc[sub["retention_pct"].idxmin()]
        fully_ret = (sub["retention_pct"] >= 95).mean() * 100  # % of cells ≥ 95%

        record_number(sec, f"{scenario} mean retention", mean_ret, ".1f")
        record_number(sec, f"{scenario} worst retention ({min_row['region_short']}/{min_row['method']})", min_ret, ".1f")
        record_number(sec, f"{scenario} % cells >= 95% retention", fully_ret, ".0f")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    print("\n" + "="*60)
    print("Supplementary: Calibration Staleness Penalty")
    print("="*60)

    df_5min = load_5min()

    # Compute parameters for every scenario
    print("\n── Computing parameters per scenario ──")
    all_params = {}
    for scenario, cfg in SCENARIOS.items():
        calib_years = cfg["calib_years"]
        print(f"  {scenario:12s}  calibrated on {calib_years}")
        all_params[scenario] = compute_params(df_5min, calib_years)

    # Run simulations
    print("\n── Running simulations ──")
    sim_results = {}
    for scenario, cfg in SCENARIOS.items():
        sim_results[scenario] = run_simulation(
            df_5min, all_params[scenario], cfg["eval_years"],
            scenario, recompute=recompute
        )

    # Aggregate per scenario
    print("\n── Aggregating ──")
    scenario_aggs = {s: aggregate_by_region_method(df) for s, df in sim_results.items()}
    summary       = build_summary(scenario_aggs)
    drift_df      = build_param_drift(all_params)

    # Print summary
    pivot = (summary[summary["scenario"] != "reference"]
             .pivot_table(index=["region_short", "method"],
                          columns="scenario", values="retention_pct")
             .round(1))
    print("\nRetention (%) relative to full-period reference:")
    print(pivot.to_string())

    # Tables
    export_cols = [
        "scenario", "region_short", "method_label",
        "mean_savings", "ci_lo", "ci_hi",
        "ref_savings", "retention_pct", "n_days"
    ]
    save_table(
        summary[export_cols].round(2),
        "table_supp_holdout_summary",
        caption=(
            "Scheduling savings and retention relative to full-period (2022-2024) reference. "
            "Stale 1yr = parameters from 2022 only evaluated on 2023-2024. "
            "Stale 2yr = parameters from 2022-2023 evaluated on 2024. "
            "Retention = stale savings / reference savings * 100."
        )
    )
    save_table(
        drift_df.round(2),
        "table_supp_holdout_param_drift",
        caption="Heuristic parameter drift from full-period reference values."
    )

    # Figures
    plot_savings_with_reference(summary)

    # Numbers
    record_key_numbers(summary)
    export_numbers()

    print("\n✅ ch3_supp_temporal_holdout complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true",
                        help="Ignore cached results and recompute simulations")
    args = parser.parse_args()
    main(recompute=args.recompute)