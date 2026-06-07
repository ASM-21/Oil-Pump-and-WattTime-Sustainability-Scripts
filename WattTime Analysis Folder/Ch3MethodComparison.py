"""
ch3_method_comparison.py — Unified Scheduling Method Comparison

Loads results from all four scheduling methods (or re-derives them if the
source CSVs are absent) and assembles a single comparison framework:

    Method              Source
    ──────────────────  ──────────────────────────────────────────────────
    Optimal             re-derived via run_scheduling_sim (perfect hindsight)
    Traffic Light       table_3_5_savings.csv  (or re-derived)
    TOD Annual          table_tod_annual_savings.csv  (or re-derived)
    TOD Seasonal        table_tod_seasonal_improvement.csv  (or re-derived)
    Forecast-guided     table_forecast_eval_summary.csv  (optional)

All methods are expressed on the same metric basis:
  - Mean daily savings vs. baseline (%)
  - Capture rate = savings / optimal savings (%)
  - Bootstrap 95% CI on savings

Outputs (ch3_outputs/):
    Tables:
        table_method_comparison.csv/md  — wide table, one row per region
        table_method_ranking.csv/md     — method rank by region + cross-region stats
    Figures:
        fig_method_comparison.png/pdf   — grouped bar chart, regions × methods
        fig_capture_rate_heatmap.png/pdf— heatmap of capture rates
    Numbers appended to ch3_numbers.md

Usage:
    python ch3_method_comparison.py
    python ch3_method_comparison.py --recompute   # ignore cached CSVs, re-derive all
"""

import argparse
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, run_scheduling_sim, compute_thresholds, simulate_day, bootstrap_ci,
    CH3_REGIONS, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    N_BOOTSTRAP, CHARACTERIZATION_YEARS,
    TL_STRATEGY,
    rlabel, rshort, rcolor,
    TABLES_DIR, FIGURES_DIR,
)

warnings.filterwarnings("ignore", category=FutureWarning)

# =============================================================================
# CONFIG
# =============================================================================

ANALYSIS_YEARS = CHARACTERIZATION_YEARS
SECTION_TAG    = "Method-Comparison"

# Method display config — order determines bar order in figure
METHODS = {
    "optimal":      {"label": "Optimal",         "color": "#1f77b4", "linestyle": "--"},
    "tl":           {"label": "Traffic Light",    "color": "#2ca02c", "linestyle": "-"},
    "tod_annual":   {"label": "TOD Annual",       "color": "#ff7f0e", "linestyle": "-"},
    "tod_seasonal": {"label": "TOD Seasonal",     "color": "#9467bd", "linestyle": "-"},
    "forecast":     {"label": "Forecast-Guided",  "color": "#e377c2", "linestyle": "-"},
}

# If True, always re-run simulations even if source CSVs exist
FORCE_RECOMPUTE = False


# =============================================================================
# REGION KEY NORMALISATION
# Builds lookup from both rlabel() and rshort() → canonical CH3 key
# =============================================================================

def _build_region_lookup() -> dict:
    lookup = {}
    for key in CH3_REGIONS:
        lookup[rlabel(key)]  = key   # "BPA (Hydro)"       → "BPA"
        lookup[rshort(key)]  = key   # "BPA"               → "BPA"
        lookup[key]          = key   # "BPA"               → "BPA"  (passthrough)
    return lookup

_REGION_LOOKUP = _build_region_lookup()

def _norm(region_str: str) -> "str | None":
    """Map any region string variant to canonical CH3 key, or None if unknown."""
    return _REGION_LOOKUP.get(str(region_str).strip())


# =============================================================================
# LOADERS — try CSV first, fall back to re-derivation
# =============================================================================

def _csv(name: str) -> "pd.DataFrame | None":
    p = TABLES_DIR / f"{name}.csv"
    if p.exists():
        df = pd.read_csv(p)
        print(f"  📂 Loaded {name}.csv  ({len(df)} rows)")
        return df
    print(f"  ⚠  {name}.csv not found — will re-derive")
    return None


def load_optimal_and_tl(df_5min: pd.DataFrame, recompute: bool) -> dict:
    """
    Returns dict: {region_key: {"optimal": float, "tl": float,
                                 "tl_lo": float, "tl_hi": float,
                                 "opt_lo": float, "opt_hi": float}}
    """
    # Try table_3_5 first
    t35 = None if recompute else _csv("table_3_5_savings")

    if t35 is not None:
        out = {}
        for _, row in t35.iterrows():
            key = _norm(row.get("Region", row.get("Archetype", "")))
            if key is None:
                # table_3_5 uses rshort — try by iterating
                for k in CH3_REGIONS:
                    if rshort(k) == str(row.get("Region", "")).strip():
                        key = k; break
            if key is None:
                continue
            opt = float(row["Optimal (%)"])
            # Canonical TL strategy column
            strat_col = {
                "first_green":      "First-Green (%)",
                "mean_green":       "Mean-Green (%)",
                "best_green":       "Best-Green (%)",
                "persistent_green": "Persistent-Green (%)",
            }.get(TL_STRATEGY, "First-Green (%)")
            tl = float(row[strat_col]) if strat_col in row else float(row["First-Green (%)"])
            # CIs stored as strings "(lo, hi)" — parse them
            ci_col = {
                "first_green": "FG 95% CI",
                "mean_green":  "MG 95% CI",
            }.get(TL_STRATEGY, "FG 95% CI")
            tl_lo = tl_hi = tl   # fallback
            if ci_col in row and isinstance(row[ci_col], str):
                try:
                    parts = row[ci_col].strip("()").split(",")
                    tl_lo, tl_hi = float(parts[0]), float(parts[1])
                except Exception:
                    pass
            out[key] = {"optimal": opt, "tl": tl,
                        "tl_lo": tl_lo, "tl_hi": tl_hi,
                        "opt_lo": opt,  "opt_hi": opt}
        return out

    # Re-derive from simulation
    print("  Re-running scheduling simulation for TL / Optimal...")
    sim_df = run_scheduling_sim(df_5min, years=ANALYSIS_YEARS,
                                use_cache=not recompute, cache_tag="method_cmp")
    out = {}
    for region, rd in sim_df.groupby("region"):
        key = _norm(region)
        if key is None: continue
        opt_vals = rd["savings_optimal_pct"].values
        tl_vals  = rd["savings_tl_pct"].values
        tl_lo, tl_hi = bootstrap_ci(tl_vals, np.mean, N_BOOTSTRAP)
        out[key] = {
            "optimal": float(np.mean(opt_vals)),
            "tl":      float(np.mean(tl_vals)),
            "tl_lo":   float(tl_lo),
            "tl_hi":   float(tl_hi),
            "opt_lo":  float(np.mean(opt_vals)),
            "opt_hi":  float(np.mean(opt_vals)),
        }
    return out


def load_tod_annual(df_5min: pd.DataFrame, recompute: bool) -> dict:
    """
    Returns dict: {region_key: {"tod_annual": float, "tod_annual_lo": float,
                                 "tod_annual_hi": float}}
    """
    tbl = None if recompute else _csv("table_tod_annual_savings")

    if tbl is not None:
        out = {}
        for _, row in tbl.iterrows():
            key = _norm(row.get("Region", ""))
            if key is None: continue
            out[key] = {
                "tod_annual":    float(row["TOD Savings (%)"]),
                "tod_annual_lo": float(row.get("95% CI Lower", row["TOD Savings (%)"])),
                "tod_annual_hi": float(row.get("95% CI Upper", row["TOD Savings (%)"])),
            }
        return out

    # Re-derive
    print("  Re-deriving TOD Annual from data...")
    from Ch3TodAnnual import compute_annual_best_hours, simulate_fixed_tod

    d = df_5min.copy()
    if ANALYSIS_YEARS:
        d = d[d["year"].isin(ANALYSIS_YEARS)]
    best_hours = compute_annual_best_hours(d)
    sim_df = simulate_fixed_tod(d, best_hours)

    out = {}
    for region, rd in sim_df.groupby("region"):
        key = _norm(region)
        if key is None: continue
        vals = rd["savings_tod_pct"].values
        lo, hi = bootstrap_ci(vals, np.mean, N_BOOTSTRAP)
        out[key] = {"tod_annual": float(np.mean(vals)),
                    "tod_annual_lo": float(lo), "tod_annual_hi": float(hi)}
    return out


def load_tod_seasonal(df_5min: pd.DataFrame, recompute: bool) -> dict:
    """
    Returns dict: {region_key: {"tod_seasonal": float, "tod_seasonal_lo": float,
                                 "tod_seasonal_hi": float}}
    """
    tbl = None if recompute else _csv("table_tod_seasonal_improvement")

    if tbl is not None:
        out = {}
        for _, row in tbl.iterrows():
            key = _norm(row.get("Region", ""))
            if key is None: continue
            s = float(row["Seasonal Savings (%)"])
            out[key] = {
                "tod_seasonal":    s,
                "tod_seasonal_lo": float(row.get("CI Lower", s)),
                "tod_seasonal_hi": float(row.get("CI Upper", s)),
            }
        return out

    # Re-derive
    print("  Re-deriving TOD Seasonal from data...")
    from Ch3TodSeasonal import compute_best_hours, apply_overrides, simulate_fixed_tod as sim_seas

    d = df_5min.copy()
    if ANALYSIS_YEARS:
        d = d[d["year"].isin(ANALYSIS_YEARS)]
    derived_annual, derived_seasonal = compute_best_hours(d)
    annual_hours, seasonal_hours = apply_overrides(derived_annual, derived_seasonal)
    sim_df = sim_seas(d, annual_hours, seasonal_hours)

    out = {}
    for region, rd in sim_df.groupby("region"):
        key = _norm(region)
        if key is None: continue
        vals = rd["savings_seasonal"].values
        lo, hi = bootstrap_ci(vals, np.mean, N_BOOTSTRAP)
        out[key] = {"tod_seasonal": float(np.mean(vals)),
                    "tod_seasonal_lo": float(lo), "tod_seasonal_hi": float(hi)}
    return out


def load_forecast(recompute: bool) -> dict:
    """
    Returns dict: {region_key: {"forecast": float, "forecast_lo": float,
                                 "forecast_hi": float, "note": str}}
    Only available for regions present in table_forecast_eval_summary.csv.
    Returns empty dict (gracefully) if the CSV doesn't exist.
    """
    tbl = None if recompute else _csv("table_forecast_eval_summary")
    if tbl is None:
        print("  ℹ Forecast summary not found — forecast column will be empty.")
        return {}

    out = {}
    for _, row in tbl.iterrows():
        key = _norm(row.get("Region", ""))
        if key is None: continue
        n   = int(row.get("N Days", 0))
        fc  = row.get("Forecast Savings (%)")
        if n == 0 or pd.isna(fc):
            out[key] = {"forecast": np.nan, "forecast_lo": np.nan,
                        "forecast_hi": np.nan,
                        "note": str(row.get("Note", "no data"))}
            continue
        out[key] = {
            "forecast":    float(fc),
            "forecast_lo": float(row.get("FC Savings 95% CI Lo", fc)),
            "forecast_hi": float(row.get("FC Savings 95% CI Hi", fc)),
            "note":        str(row.get("Note", "")),
        }
    return out


# =============================================================================
# BUILD UNIFIED TABLE
# =============================================================================

def build_comparison_table(tl_opt: dict, tod_ann: dict,
                           tod_seas: dict, forecast: dict) -> pd.DataFrame:
    rows = []
    for key in CH3_REGIONS:
        opt  = tl_opt.get(key, {})
        ann  = tod_ann.get(key, {})
        seas = tod_seas.get(key, {})
        fc   = forecast.get(key, {})

        optimal_sav     = opt.get("optimal",      np.nan)
        tl_sav          = opt.get("tl",           np.nan)
        tl_lo           = opt.get("tl_lo",        np.nan)
        tl_hi           = opt.get("tl_hi",        np.nan)
        tod_annual_sav  = ann.get("tod_annual",   np.nan)
        ann_lo          = ann.get("tod_annual_lo",np.nan)
        ann_hi          = ann.get("tod_annual_hi",np.nan)
        tod_seas_sav    = seas.get("tod_seasonal",np.nan)
        seas_lo         = seas.get("tod_seasonal_lo", np.nan)
        seas_hi         = seas.get("tod_seasonal_hi", np.nan)
        fc_sav          = fc.get("forecast",      np.nan)
        fc_lo           = fc.get("forecast_lo",   np.nan)
        fc_hi           = fc.get("forecast_hi",   np.nan)

        def _cap(s):
            return round(s / optimal_sav * 100, 1) if (
                not np.isnan(s) and not np.isnan(optimal_sav) and optimal_sav > 0
            ) else np.nan

        # Best practical method (excluding optimal; NaN-safe)
        practical = {
            "Traffic Light":  tl_sav,
            "TOD Annual":     tod_annual_sav,
            "TOD Seasonal":   tod_seas_sav,
            "Forecast":       fc_sav,
        }
        valid_practical = {k: v for k, v in practical.items() if not np.isnan(v)}
        best_method = max(valid_practical, key=valid_practical.get) if valid_practical else "—"
        best_value  = valid_practical.get(best_method, np.nan)

        rows.append({
            "Region":                  rlabel(key),
            "Short":                   rshort(key),
            "Archetype":               CH3_REGIONS[key]["archetype"],
            # Savings columns
            "Optimal (%)":             round(optimal_sav, 1) if not np.isnan(optimal_sav) else np.nan,
            "Traffic Light (%)":       round(tl_sav, 1)       if not np.isnan(tl_sav)      else np.nan,
            "TL 95% CI":               f"({tl_lo:.1f}, {tl_hi:.1f})" if not np.isnan(tl_lo) else "—",
            "TOD Annual (%)":          round(tod_annual_sav, 1) if not np.isnan(tod_annual_sav) else np.nan,
            "Ann 95% CI":              f"({ann_lo:.1f}, {ann_hi:.1f})" if not np.isnan(ann_lo) else "—",
            "TOD Seasonal (%)":        round(tod_seas_sav, 1)  if not np.isnan(tod_seas_sav)  else np.nan,
            "Seas 95% CI":             f"({seas_lo:.1f}, {seas_hi:.1f})" if not np.isnan(seas_lo) else "—",
            "Forecast (%)":            round(fc_sav, 1)         if not np.isnan(fc_sav)       else np.nan,
            "FC 95% CI":               f"({fc_lo:.1f}, {fc_hi:.1f})" if not np.isnan(fc_lo) else "—",
            # Capture rates
            "TL Capture (%)":          _cap(tl_sav),
            "TOD Annual Capture (%)":  _cap(tod_annual_sav),
            "TOD Seasonal Capture (%)":_cap(tod_seas_sav),
            "Forecast Capture (%)":    _cap(fc_sav),
            # Meta
            "Best Practical Method":   best_method,
            "Best Practical Sav (%)":  round(best_value, 1) if not np.isnan(best_value) else np.nan,
        })

        record_number(SECTION_TAG, f"{rshort(key)} TL savings %",        tl_sav,        ".1f")
        record_number(SECTION_TAG, f"{rshort(key)} TOD Annual savings %", tod_annual_sav,".1f")
        record_number(SECTION_TAG, f"{rshort(key)} TOD Seasonal savings %",tod_seas_sav, ".1f")
        if not np.isnan(fc_sav):
            record_number(SECTION_TAG, f"{rshort(key)} Forecast savings %", fc_sav, ".1f")

    return pd.DataFrame(rows)


def build_ranking_table(comp: pd.DataFrame) -> pd.DataFrame:
    """
    For each region, rank the practical methods by savings.
    Append cross-region summary stats per method.
    """
    method_cols = {
        "Traffic Light":  "Traffic Light (%)",
        "TOD Annual":     "TOD Annual (%)",
        "TOD Seasonal":   "TOD Seasonal (%)",
        "Forecast":       "Forecast (%)",
    }

    rows = []
    for _, row in comp.iterrows():
        vals = {m: row[c] for m, c in method_cols.items()
                if not pd.isna(row.get(c))}
        ranked = sorted(vals, key=vals.get, reverse=True)
        rank_str = " > ".join(f"{m} ({vals[m]:.1f}%)" for m in ranked)
        rows.append({
            "Region":   row["Short"],
            "Archetype":row["Archetype"],
            "Ranking":  rank_str,
            "Best Method": ranked[0] if ranked else "—",
            "Best Savings (%)": round(vals[ranked[0]], 1) if ranked else np.nan,
        })

    df = pd.DataFrame(rows)

    # Append cross-region summary row
    summary_parts = {}
    for m, c in method_cols.items():
        vals_all = comp[c].dropna().values
        if len(vals_all):
            summary_parts[m] = f"{np.mean(vals_all):.1f}% (range {np.min(vals_all):.1f}–{np.max(vals_all):.1f}%)"
            record_number(SECTION_TAG, f"Cross-region mean {m} savings %",
                          float(np.mean(vals_all)), ".1f")

    summary_row = pd.DataFrame([{
        "Region":       "CROSS-REGION",
        "Archetype":    "All regions",
        "Ranking":      " | ".join(f"{m}: {v}" for m, v in summary_parts.items()),
        "Best Method":  "—",
        "Best Savings (%)": np.nan,
    }])
    df = pd.concat([df, summary_row], ignore_index=True)

    return df


# =============================================================================
# FIGURES
# =============================================================================

def plot_grouped_bars(comp: pd.DataFrame):
    """
    Grouped bar chart: for each region (x-axis), one bar per method.
    Height = mean savings %, with CI error bars where available.
    """
    method_configs = [
        ("Optimal (%)",      None,      None,      METHODS["optimal"],      False),
        ("Traffic Light (%)", "TL 95% CI", None,   METHODS["tl"],           True),
        ("TOD Annual (%)",    "Ann 95% CI", None,  METHODS["tod_annual"],    True),
        ("TOD Seasonal (%)",  "Seas 95% CI", None, METHODS["tod_seasonal"],  True),
        ("Forecast (%)",      "FC 95% CI", None,   METHODS["forecast"],      True),
    ]

    # Parse CI strings into lo/hi arrays
    def _parse_ci(ci_str, center):
        try:
            parts = str(ci_str).strip("()").split(",")
            lo = center - float(parts[0])
            hi = float(parts[1]) - center
            return max(lo, 0), max(hi, 0)
        except Exception:
            return 0, 0

    region_keys   = list(CH3_REGIONS.keys())
    region_labels = [rshort(r) for r in region_keys]
    n_regions     = len(region_keys)

    # Determine which methods have any data
    active = []
    for col, ci_col, _, mcfg, show_ci in method_configs:
        vals = [comp.loc[comp["Short"] == rshort(r), col].values
                for r in region_keys]
        vals = [v[0] if len(v) > 0 and not np.isnan(v[0]) else np.nan for v in vals]
        if any(not np.isnan(v) for v in vals):
            active.append((col, ci_col, mcfg, show_ci, vals))

    n_methods = len(active)
    w         = 0.8 / n_methods
    x         = np.arange(n_regions)

    with thesis_style():
        fig, ax = plt.subplots(figsize=(13, 5))

        for mi, (col, ci_col, mcfg, show_ci, vals) in enumerate(active):
            offset  = (mi - (n_methods - 1) / 2) * w
            colors  = []
            ci_lo   = []
            ci_hi   = []

            for ri, rk in enumerate(region_keys):
                v = vals[ri]
                colors.append(mcfg["color"] if not np.isnan(v) else "#eeeeee")
                if ci_col and not np.isnan(v):
                    ci_str = comp.loc[comp["Short"] == rshort(rk), ci_col].values
                    ci_str = ci_str[0] if len(ci_str) > 0 else "—"
                    lo, hi = _parse_ci(ci_str, v)
                else:
                    lo, hi = 0, 0
                ci_lo.append(lo)
                ci_hi.append(hi)

            heights = [v if not np.isnan(v) else 0 for v in vals]
            ax.bar(x + offset, heights, width=w * 0.92,
                   color=mcfg["color"], alpha=0.85,
                   label=mcfg["label"], zorder=3)

            if show_ci and any(l > 0 or h > 0 for l, h in zip(ci_lo, ci_hi)):
                valid_x  = [x[i] + offset for i in range(n_regions) if not np.isnan(vals[i])]
                valid_h  = [heights[i]   for i in range(n_regions) if not np.isnan(vals[i])]
                valid_lo = [ci_lo[i]     for i in range(n_regions) if not np.isnan(vals[i])]
                valid_hi = [ci_hi[i]     for i in range(n_regions) if not np.isnan(vals[i])]
                if valid_x:
                    ax.errorbar(valid_x, valid_h, yerr=[valid_lo, valid_hi],
                                fmt="none", color="black", capsize=2.5,
                                linewidth=0.9, zorder=4)

        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(
            [f"{rshort(r)}\n{CH3_REGIONS[r]['archetype']}" for r in region_keys],
            fontsize=16
        )
        ax.set_ylabel("Mean Daily Savings vs. Baseline (%)")

        # Clean legend — deduplicate
        handles, labels_leg = ax.get_legend_handles_labels()
        seen = {}
        for h, l in zip(handles, labels_leg):
            if l not in seen:
                seen[l] = h
        ax.legend(seen.values(), seen.keys(), fontsize=14, loc="upper center",bbox_to_anchor=(.65,1),
                  framealpha=0.9, ncol=2)

        fig.tight_layout()
        save_fig(fig, "fig_method_comparison")


def plot_capture_heatmap(comp: pd.DataFrame):
    """
    Heatmap: rows = regions, cols = practical methods, cells = capture rate %.
    """
    cap_cols = {
        "Traffic Light":   "TL Capture (%)",
        "TOD Annual":      "TOD Annual Capture (%)",
        "TOD Seasonal":    "TOD Seasonal Capture (%)",
        "Forecast":        "Forecast Capture (%)",
    }

    region_keys = [r for r in CH3_REGIONS
                   if rshort(r) in comp["Short"].values]
    row_labels  = [f"{rshort(r)}\n({CH3_REGIONS[r]['archetype']})" for r in region_keys]

    # Build matrix — only include methods with any data
    active_methods = {m: c for m, c in cap_cols.items()
                      if comp[c].notna().any()}
    if not active_methods:
        print("  ⚠ No capture rate data — skipping heatmap")
        return

    col_labels = list(active_methods.keys())
    matrix     = np.full((len(region_keys), len(col_labels)), np.nan)

    for ri, rk in enumerate(region_keys):
        row = comp[comp["Short"] == rshort(rk)]
        for ci, (m, c) in enumerate(active_methods.items()):
            val = row[c].values
            if len(val) > 0 and not np.isnan(val[0]):
                matrix[ri, ci] = val[0]

    with thesis_style():
        fig, ax = plt.subplots(figsize=(7, 4))

        # Mask NaN cells
        masked = np.ma.masked_invalid(matrix)
        cmap   = plt.cm.RdYlGn.copy()
        cmap.set_bad("#f0f0f0")

        im = ax.imshow(masked, cmap=cmap, aspect="auto", vmin=0, vmax=100)

        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, fontsize=9)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=8)

        # Annotate cells
        for ri in range(len(region_keys)):
            for ci in range(len(col_labels)):
                val = matrix[ri, ci]
                if not np.isnan(val):
                    text_color = "white" if val > 75 or val < 25 else "black"
                    ax.text(ci, ri, f"{val:.0f}%",
                            ha="center", va="center",
                            fontsize=9, color=text_color, fontweight="bold")
                else:
                    ax.text(ci, ri, "—", ha="center", va="center",
                            fontsize=9, color="#aaaaaa")

        cbar = fig.colorbar(im, ax=ax, shrink=0.85)
        cbar.set_label("Capture Rate (%)\n(Method Savings / Optimal Savings)", fontsize=8)

        fig.tight_layout()
        save_fig(fig, "fig_capture_rate_heatmap")



# =============================================================================
# TABLE 3-2: ARCHETYPE SCHEDULING METRICS
# =============================================================================

def build_table_3_2(df_5min: pd.DataFrame, sim_df: pd.DataFrame) -> pd.DataFrame:
    """
    Reproduces Table 3-2 format:
        Archetype | Region | Baseline MOER | Optimal MOER | Savings % |
        CO2 Saved/2kWh (g) | Diurnal Range (lbs/MWh)

    sim_df: day-level simulation results from run_scheduling_sim
            (must have columns: region, baseline_moer, optimal_moer,
             savings_optimal_pct)
    df_5min: 5-min actuals, used for diurnal range calculation
    """
    # Diurnal range: max - min of mean hourly MOER within shift window
    win = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ]
    diurnal = {}
    for region in CH3_REGIONS:
        rd = win[win["region"] == region]
        if len(rd) == 0:
            diurnal[region] = np.nan
            continue
        hourly_mean = rd.groupby("hour")["value"].mean()
        diurnal[region] = float(hourly_mean.max() - hourly_mean.min())

    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        if len(rd) == 0:
            continue

        baseline_moer = float(rd["baseline_moer"].mean())
        optimal_moer  = float(rd["optimal_moer"].mean())
        savings_pct   = float(rd["savings_optimal_pct"].mean())

        rows.append({
            "Archetype":               CH3_REGIONS[region]["archetype"],
            "Region":                  rshort(region),
            "Baseline MOER (lbs/MWh)": round(baseline_moer),
            "Optimal MOER (lbs/MWh)":  round(optimal_moer),
            "Savings (%)":             round(savings_pct, 1),
            "Diurnal Range (lbs/MWh)": round(diurnal.get(region, np.nan)),
        })

        record_number("Table 3-2", f"{rshort(region)} baseline MOER",     baseline_moer, ".0f")
        record_number("Table 3-2", f"{rshort(region)} optimal MOER",      optimal_moer,  ".0f")
        record_number("Table 3-2", f"{rshort(region)} optimal savings %",  savings_pct,   ".1f")
        record_number("Table 3-2", f"{rshort(region)} diurnal range",
                      diurnal.get(region, np.nan), ".0f")

    return pd.DataFrame(rows)

# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    recompute = recompute or FORCE_RECOMPUTE
    print(f"\n── Method Comparison  (recompute={recompute}) ──")

    # ── Load 5-min data (needed for re-derivation paths) ─────────────────────
    df_5min = load_5min()
    if ANALYSIS_YEARS:
        df_5min = df_5min[df_5min["year"].isin(ANALYSIS_YEARS)].copy()
        print(f"  Filtered to years: {ANALYSIS_YEARS}")

    # ── Run/load simulation (needed for Table 3-2 and TL/Optimal) ──────────
    print("\n[1] Loading Optimal + Traffic Light (+ simulation for Table 3-2)...")
    # Always get the sim_df for Table 3-2; load_optimal_and_tl may use CSV shortcut
    sim_df_full = run_scheduling_sim(df_5min, years=ANALYSIS_YEARS,
                                     use_cache=not recompute, cache_tag="method_cmp")
    tl_opt   = load_optimal_and_tl(df_5min, recompute)

    print("\n[2] Loading TOD Annual...")
    tod_ann  = load_tod_annual(df_5min, recompute)

    print("\n[3] Loading TOD Seasonal...")
    tod_seas = load_tod_seasonal(df_5min, recompute)

    print("\n[4] Loading Forecast (optional)...")
    forecast = load_forecast(recompute)

    # ── Table 3-2: archetype scheduling metrics ─────────────────────────────
    print("\n[4b] Building Table 3-2...")
    table_3_2 = build_table_3_2(df_5min, sim_df_full)
    print(table_3_2.to_string(index=False))
    save_table(table_3_2, "table_3_2_archetype_metrics",
               caption="Table 3-2. Archetype scheduling metrics for a 2-hour day-shift reference job.")

    # ── Build unified comparison table ───────────────────────────────────────
    print("\n[5] Building comparison table...")
    comp = build_comparison_table(tl_opt, tod_ann, tod_seas, forecast)

    # Pretty-print key columns
    display_cols = ["Short", "Archetype", "Optimal (%)",
                    "Traffic Light (%)", "TOD Annual (%)",
                    "TOD Seasonal (%)", "Forecast (%)",
                    "Best Practical Method"]
    print("\n" + comp[display_cols].to_string(index=False))

    save_table(comp, "table_method_comparison",
               caption=(f"Scheduling Method Comparison: Mean Daily Savings vs. Baseline (%) "
                        f"— {ANALYSIS_YEARS[0]}–{ANALYSIS_YEARS[-1]}"))

    # ── Ranking table ─────────────────────────────────────────────────────────
    print("\n[6] Building ranking table...")
    ranking = build_ranking_table(comp)
    print(ranking[["Region", "Archetype", "Best Method", "Best Savings (%)"]].to_string(index=False))
    save_table(ranking, "table_method_ranking",
               caption="Method Ranking by Region (best practical method and cross-region statistics)")

    # ── Figures ───────────────────────────────────────────────────────────────
    print("\n[7] Plotting...")
    plot_grouped_bars(comp)
    plot_capture_heatmap(comp)

    # ── Cross-region summary numbers ──────────────────────────────────────────
    for m, c in [("TL",          "Traffic Light (%)"),
                 ("TOD Annual",   "TOD Annual (%)"),
                 ("TOD Seasonal", "TOD Seasonal (%)"),
                 ("Forecast",     "Forecast (%)")]:
        vals = comp[c].dropna().values
        if len(vals):
            record_number(SECTION_TAG, f"{m} mean savings all regions %",
                          float(np.mean(vals)), ".1f")
            record_number(SECTION_TAG, f"{m} min savings %",
                          float(np.min(vals)), ".1f")
            record_number(SECTION_TAG, f"{m} max savings %",
                          float(np.max(vals)), ".1f")

    # Best method counts
    counts = comp["Best Practical Method"].value_counts()
    for m, n in counts.items():
        record_number(SECTION_TAG, f"Regions where {m} is best", int(n))

    export_numbers()
    print("\n✅ ch3_method_comparison.py complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true",
                        help="Ignore cached CSVs and re-derive all methods from data")
    args = parser.parse_args()
    main(recompute=args.recompute)