"""
ch3_tod_seasonal.py — Seasonal Fixed Time-of-Day Scheduling Analysis

Simulates a 2-hr reference job starting at the season-specific best hour for
each region. Benchmarks against:
  (1) baseline — uniform random start within shift window
  (2) optimal  — perfect hindsight oracle
  (3) annual TOD — single fixed best hour (from ch3_tod_annual.py)

Key question: does swapping to a season-aware rule meaningfully improve on the
simpler annual rule, and by how much varies by archetype?

Outputs:
    Tables:
        table_tod_seasonal_savings.csv/md       — savings % and capture rate by region × season
        table_tod_seasonal_improvement.csv/md   — seasonal gain over annual rule, by region
    Figures:
        fig_tod_seasonal_savings.png/pdf        — heatmap: TOD savings % by region × season
        fig_tod_seasonal_improvement.png/pdf    — bar chart: improvement over annual rule
    Numbers appended to ch3_numbers.md

Usage:
    python ch3_tod_seasonal.py
    python ch3_tod_seasonal.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, compute_thresholds, simulate_day, bootstrap_ci,
    CH3_REGIONS, SEASON_ORDER, SEASON_COLORS, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    N_BOOTSTRAP, CHARACTERIZATION_YEARS,
    rlabel, rshort, rcolor,
    TABLES_DIR, FIGURES_DIR,
)

# =============================================================================
# CONFIG
# =============================================================================

# Season-specific best hours from Table 3-3 (integer hour, 24-hr, in 6–17).
# Set any to None to derive from data instead.
# Outer key = region key, inner key = season string matching SEASON_ORDER.
SEASONAL_BEST_HOUR_OVERRIDE = {
    "BPA":                {"winter": None, "spring": None, "summer": None, "fall": None},
    "CAISO_NORTH":        {"winter": None, "spring": None, "summer": None, "fall": None},
    "ERCOT_NORTHCENTRAL": {"winter": None, "spring": None, "summer": None, "fall": None},
    "ISONE_CT":           {"winter": None, "spring": None, "summer": None, "fall": None},
    "MISO_INDIANAPOLIS":  {"winter": None, "spring": None, "summer": None, "fall": None},
    "SPP_KANSAS":         {"winter": None, "spring": None, "summer": None, "fall": None},
}

# Annual best hours from ch3_tod_annual (used for comparison column).
# Set to None for any region to re-derive from data.
ANNUAL_BEST_HOUR_OVERRIDE = {
    "BPA":                None,
    "CAISO_NORTH":        None,
    "ERCOT_NORTHCENTRAL": None,
    "ISONE_CT":           None,
    "MISO_INDIANAPOLIS":  None,
    "SPP_KANSAS":         None,
}

ANALYSIS_YEARS = CHARACTERIZATION_YEARS
SECTION_TAG    = "TOD-Seasonal"


# =============================================================================
# STEP 1 — Derive best hours (annual + seasonal) from data
# =============================================================================

def compute_best_hours(df_5min: pd.DataFrame):
    """
    Returns:
        annual_hours   : {region: int}
        seasonal_hours : {region: {season: int}}
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)

    win = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].copy()

    annual_hours   = {}
    seasonal_hours = {r: {} for r in CH3_REGIONS}

    for region in CH3_REGIONS:
        rd = win[win["region"] == region].sort_values("point_time_local")
        if len(rd) == 0:
            print(f"  ⚠ No data: {region}")
            continue

        # ── annual ───────────────────────────────────────────────────────────
        hour_means_all = {}
        for date, ddf in rd.groupby("date"):
            vals = ddf["value"].values
            hrs  = ddf["hour"].values
            if len(vals) < job_intervals:
                continue
            for i in range(len(vals) - job_intervals + 1):
                h = int(hrs[i])
                wm = float(vals[i:i + job_intervals].mean())
                hour_means_all.setdefault(h, []).append(wm)

        if hour_means_all:
            annual_hours[region] = min(hour_means_all,
                                       key=lambda h: np.mean(hour_means_all[h]))

        # ── seasonal ─────────────────────────────────────────────────────────
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                continue
            hour_means_s = {}
            for date, ddf in sd.groupby("date"):
                vals = ddf["value"].values
                hrs  = ddf["hour"].values
                if len(vals) < job_intervals:
                    continue
                for i in range(len(vals) - job_intervals + 1):
                    h = int(hrs[i])
                    wm = float(vals[i:i + job_intervals].mean())
                    hour_means_s.setdefault(h, []).append(wm)
            if hour_means_s:
                seasonal_hours[region][season] = min(
                    hour_means_s, key=lambda h: np.mean(hour_means_s[h])
                )

        # Summary print
        ann = annual_hours.get(region, "?")
        seas_str = "  ".join(
            f"{s[:2]}={seasonal_hours[region].get(s,'?'):>2}"
            for s in SEASON_ORDER
        )
        print(f"  {rshort(region):10s}  annual={ann:>2}  [{seas_str}]")

    return annual_hours, seasonal_hours


def apply_overrides(derived_annual, derived_seasonal):
    annual   = {}
    seasonal = {r: {} for r in CH3_REGIONS}

    for region in CH3_REGIONS:
        # Annual
        ov = ANNUAL_BEST_HOUR_OVERRIDE.get(region)
        annual[region] = ov if ov is not None else derived_annual.get(region)

        # Seasonal
        for season in SEASON_ORDER:
            ov_s = SEASONAL_BEST_HOUR_OVERRIDE.get(region, {}).get(season)
            seasonal[region][season] = (
                ov_s if ov_s is not None
                else derived_seasonal.get(region, {}).get(season)
            )

    return annual, seasonal


# =============================================================================
# STEP 2 — Fixed-TOD simulation (seasonal and annual side-by-side)
# =============================================================================

def simulate_fixed_tod(df_5min, annual_hours, seasonal_hours):
    """
    For each (region, date), run three comparisons:
      - baseline / optimal (from simulate_day)
      - seasonal TOD (job starts at season-specific best hour)
      - annual  TOD (job starts at annual best hour)

    Returns long DataFrame, one row per (region, date).
    """
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)

    thresholds = compute_thresholds(df_5min)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"])
          for _, r in thresholds.iterrows()}

    win = df_5min[
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] < DAY_SHIFT_END)
    ].copy()
    if ANALYSIS_YEARS:
        win = win[win["year"].isin(ANALYSIS_YEARS)]

    records = []

    for region in CH3_REGIONS:
        if region not in td:
            continue
        gt, rt = td[region]
        ann_h = annual_hours.get(region)
        rd = win[win["region"] == region].sort_values("point_time_local")
        skipped = 0

        for date, ddf in rd.groupby("date"):
            vals   = ddf["value"].values
            hours  = ddf["hour"].values
            season = ddf["season"].iloc[0]

            sim = simulate_day(vals, job_intervals, gt, rt)
            if sim is None:
                skipped += 1
                continue

            baseline = sim["baseline_moer"]
            optimal  = sim["optimal_moer"]

            def _tod_moer(best_h):
                if best_h is None:
                    return None
                idx = np.where(hours == best_h)[0]
                if len(idx) == 0 or idx[0] + job_intervals > len(vals):
                    return None
                return float(vals[idx[0]:idx[0] + job_intervals].mean())

            seas_h    = seasonal_hours.get(region, {}).get(season)
            seas_moer = _tod_moer(seas_h)
            ann_moer  = _tod_moer(ann_h)

            if seas_moer is None:
                skipped += 1
                continue

            def _savings(moer):
                return (baseline - moer) / baseline * 100 if baseline > 0 else 0.0

            def _capture(sav):
                opt_sav = _savings(optimal)
                return sav / opt_sav if opt_sav > 0 else (1.0 if sav >= 0 else 0.0)

            sav_seas = _savings(seas_moer)
            sav_ann  = _savings(ann_moer) if ann_moer is not None else np.nan
            sav_opt  = _savings(optimal)

            records.append({
                "region":           region,
                "date":             date,
                "year":             int(ddf["year"].iloc[0]),
                "month":            int(ddf["month"].iloc[0]),
                "season":           season,
                "seasonal_hour":    seas_h,
                "annual_hour":      ann_h,
                "seasonal_moer":    seas_moer,
                "annual_moer":      ann_moer,
                "baseline_moer":    baseline,
                "optimal_moer":     optimal,
                "savings_seasonal": sav_seas,
                "savings_annual":   sav_ann,
                "savings_optimal":  sav_opt,
                "capture_seasonal": _capture(sav_seas),
                "capture_annual":   _capture(sav_ann) if not np.isnan(sav_ann) else np.nan,
                "improvement_over_annual": sav_seas - sav_ann
                    if not np.isnan(sav_ann) else np.nan,
            })

        n_done = len([r for r in records if r["region"] == region])
        print(f"  {rshort(region):10s}  {n_done:,} days  ({skipped} skipped)")

    return pd.DataFrame(records)


# =============================================================================
# STEP 3 — Summary tables
# =============================================================================

def build_region_season_table(sim_df: pd.DataFrame) -> pd.DataFrame:
    """One row per region × season."""
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0:
                continue

            sh = sd["seasonal_hour"].iloc[0]
            ah = sd["annual_hour"].iloc[0]

            sav_s = sd["savings_seasonal"].values
            sav_a = sd["savings_annual"].dropna().values
            imp   = sd["improvement_over_annual"].dropna().values
            cap_s = np.clip(sd["capture_seasonal"].values, 0, 1) * 100

            sav_s_mean = float(np.mean(sav_s))
            sav_a_mean = float(np.mean(sav_a)) if len(sav_a) else np.nan
            imp_mean   = float(np.mean(imp))   if len(imp)   else np.nan
            cap_mean   = float(np.mean(cap_s))

            slo, shi = bootstrap_ci(sav_s, np.mean, N_BOOTSTRAP)

            rows.append({
                "Region":              rlabel(region),
                "Season":              season.capitalize(),
                "Seasonal Hour":       f"{int(sh):02d}:00" if pd.notna(sh) else "—",
                "Annual Hour":         f"{int(ah):02d}:00" if pd.notna(ah) else "—",
                "Seasonal Savings (%)":round(sav_s_mean, 1),
                "95% CI Lower":        round(slo, 1),
                "95% CI Upper":        round(shi, 1),
                "Annual Savings (%)":  round(sav_a_mean, 1) if not np.isnan(sav_a_mean) else np.nan,
                "Improvement (pp)":    round(imp_mean, 1)   if not np.isnan(imp_mean)   else np.nan,
                "Capture Rate (%)":    round(cap_mean, 1),
                "N Days":              len(sd),
            })

            record_number(SECTION_TAG,
                          f"{rshort(region)} {season} seasonal savings %",
                          sav_s_mean, ".1f")
            if not np.isnan(imp_mean):
                record_number(SECTION_TAG,
                              f"{rshort(region)} {season} improvement over annual (pp)",
                              imp_mean, ".1f")

    return pd.DataFrame(rows)


def build_region_improvement_table(sim_df: pd.DataFrame) -> pd.DataFrame:
    """One row per region — mean improvement over annual rule across all seasons."""
    rows = []
    for region in CH3_REGIONS:
        rd = sim_df[sim_df["region"] == region]
        imp = rd["improvement_over_annual"].dropna().values
        if len(imp) == 0:
            continue

        imp_mean = float(np.mean(imp))
        imp_lo, imp_hi = bootstrap_ci(imp, np.mean, N_BOOTSTRAP)

        sav_s = float(np.mean(rd["savings_seasonal"].values))
        sav_a_vals = rd["savings_annual"].dropna().values
        sav_a = float(np.mean(sav_a_vals)) if len(sav_a_vals) else np.nan

        rows.append({
            "Region":                 rlabel(region),
            "Archetype":              CH3_REGIONS[region]["archetype"],
            "Seasonal Savings (%)":   round(sav_s, 1),
            "Annual Savings (%)":     round(sav_a, 1) if not np.isnan(sav_a) else np.nan,
            "Mean Improvement (pp)":  round(imp_mean, 1),
            "CI Lower":               round(imp_lo, 1),
            "CI Upper":               round(imp_hi, 1),
        })

        record_number(SECTION_TAG,
                      f"{rshort(region)} mean improvement over annual (pp)",
                      imp_mean, ".2f")

    return pd.DataFrame(rows)


# =============================================================================
# STEP 4 — Figures
# =============================================================================

def plot_savings_heatmap(rs_table: pd.DataFrame):
    """
    Heatmap: rows = regions, cols = seasons, cells = seasonal TOD savings %.
    Side-by-side with annual savings for reference.
    """
    pivot = rs_table.pivot(index="Region", columns="Season",
                           values="Seasonal Savings (%)")
    # Reorder rows to CH3_REGIONS order
    row_order = [rlabel(r) for r in CH3_REGIONS if rlabel(r) in pivot.index]
    col_order  = [s.capitalize() for s in SEASON_ORDER if s.capitalize() in pivot.columns]
    pivot = pivot.loc[row_order, col_order]

    with thesis_style():
        fig, ax = plt.subplots(figsize=(7, 4))
        im = ax.imshow(pivot.values.astype(float), cmap="RdYlGn",
                       aspect="auto", vmin=-5, vmax=max(15, pivot.values.max() * 1.1))

        ax.set_xticks(range(len(col_order)))
        ax.set_xticklabels(col_order, fontsize=10)
        short_rows = [r.split("(")[0].strip() for r in row_order]
        ax.set_yticks(range(len(short_rows)))
        ax.set_yticklabels(short_rows, fontsize=9)

        # Annotate cells
        for i in range(len(row_order)):
            for j in range(len(col_order)):
                val = pivot.values[i, j]
                if not np.isnan(val):
                    ax.text(j, i, f"{val:.1f}%", ha="center", va="center",
                            fontsize=9,
                            color="white" if abs(val) > 10 else "black")

        cbar = fig.colorbar(im, ax=ax, shrink=0.85)
        cbar.set_label("TOD Savings vs. Baseline (%)", fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("")
        fig.tight_layout()
        save_fig(fig, "fig_tod_seasonal_savings")


def plot_improvement_bars(reg_table: pd.DataFrame):
    """
    Grouped bar: seasonal savings vs annual savings per region,
    with improvement (pp) annotated above.
    """
    row_order = [rlabel(r) for r in CH3_REGIONS
                 if rlabel(r) in reg_table["Region"].values]
    reg_table = reg_table.set_index("Region").loc[row_order].reset_index()

    labels    = [r.split("(")[0].strip() for r in reg_table["Region"]]
    sav_s     = reg_table["Seasonal Savings (%)"].values.astype(float)
    sav_a     = reg_table["Annual Savings (%)"].values.astype(float)
    imp       = reg_table["Mean Improvement (pp)"].values.astype(float)
    ci_lo     = (reg_table["Mean Improvement (pp)"] - reg_table["CI Lower"]).values.astype(float)
    ci_hi     = (reg_table["CI Upper"] - reg_table["Mean Improvement (pp)"]).values.astype(float)
    colors    = [rcolor(r) for r in CH3_REGIONS if rlabel(r) in reg_table["Region"].values]

    x = np.arange(len(labels))
    w = 0.35

    with thesis_style():
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7),
                                        gridspec_kw={"height_ratios": [2, 1]})

        # ── Top: savings comparison ──────────────────────────────────────────
        ax1.bar(x - w/2, sav_a,  width=w, color="#cccccc", label="Annual TOD",  zorder=2)
        ax1.bar(x + w/2, sav_s,  width=w, color=colors,    label="Seasonal TOD", zorder=3, alpha=0.9)
        ax1.axhline(0, color="black", linewidth=0.8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
        ax1.set_ylabel("Mean Savings vs. Baseline (%)")
        patch_a = mpatches.Patch(color="#cccccc",  label="Annual TOD")
        patch_s = mpatches.Patch(color="#555555",  label="Seasonal TOD")
        ax1.legend(handles=[patch_a, patch_s], fontsize=9, loc="upper right")

        # ── Bottom: improvement over annual ─────────────────────────────────
        bar_colors = ["#2ca02c" if v >= 0 else "#d62728" for v in imp]
        ax2.bar(x, imp, width=0.5, color=bar_colors, zorder=3)
        ax2.errorbar(x, imp, yerr=[ci_lo, ci_hi],
                     fmt="none", color="black", capsize=4, linewidth=1.2, zorder=4)
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
        ax2.set_ylabel("Improvement over\nAnnual TOD (pp)")

        # Annotate improvement values
        for xi, (v, clo, chi) in enumerate(zip(imp, ci_lo, ci_hi)):
            offset = max(chi, 0.2) + 0.1
            ax2.text(xi, v + offset if v >= 0 else v - offset,
                     f"{v:+.1f}pp", ha="center",
                     va="bottom" if v >= 0 else "top", fontsize=8)

        fig.tight_layout()
        save_fig(fig, "fig_tod_seasonal_improvement")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()
    print("\n── TOD Seasonal Best Hour Analysis ──")

    df_5min = load_5min()
    if ANALYSIS_YEARS:
        df_5min = df_5min[df_5min["year"].isin(ANALYSIS_YEARS)].copy()
        print(f"  Filtered to years: {ANALYSIS_YEARS}")

    # ── Derive / override best hours ─────────────────────────────────────────
    print("\n[1] Computing best hours (annual + seasonal)...")
    derived_annual, derived_seasonal = compute_best_hours(df_5min)
    annual_hours, seasonal_hours = apply_overrides(derived_annual, derived_seasonal)

    # Print resolved hours
    print("\n  Resolved best hours (A=annual, W/Sp/Su/F=seasonal):")
    for region in CH3_REGIONS:
        ann = annual_hours.get(region, "?")
        sh  = seasonal_hours.get(region, {})
        seas_str = "  ".join(
            f"{s[:2]}={sh.get(s,'?')}" for s in SEASON_ORDER
        )
        print(f"    {rshort(region):10s}  A={ann}  [{seas_str}]")

    # ── Simulation ───────────────────────────────────────────────────────────
    print("\n[2] Running fixed-TOD simulation (seasonal + annual)...")
    sim_df = simulate_fixed_tod(df_5min, annual_hours, seasonal_hours)

    if sim_df.empty:
        print("  ✗ No results — check data and best hours.")
        return

    print(f"\n  Total region-days: {len(sim_df):,}")

    # ── Tables ───────────────────────────────────────────────────────────────
    print("\n[3] Building summary tables...")
    rs_table  = build_region_season_table(sim_df)
    reg_table = build_region_improvement_table(sim_df)

    print("\n  Region × Season savings:")
    print(rs_table[["Region","Season","Seasonal Hour","Seasonal Savings (%)","Improvement (pp)"]].to_string(index=False))

    print("\n  Per-region improvement over annual:")
    print(reg_table.to_string(index=False))

    save_table(rs_table,  "table_tod_seasonal_savings",
               caption="Seasonal TOD Scheduling: Savings vs. Baseline by Region × Season")
    save_table(reg_table, "table_tod_seasonal_improvement",
               caption="Seasonal TOD: Mean Improvement over Annual Rule by Region")

    # ── Figures ──────────────────────────────────────────────────────────────
    print("\n[4] Plotting...")
    plot_savings_heatmap(rs_table)
    plot_improvement_bars(reg_table)

    export_numbers()
    print("\n✅ ch3_tod_seasonal.py complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)