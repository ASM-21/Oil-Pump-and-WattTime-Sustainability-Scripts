"""
ch3_extended_three_tier_signals.py — Does your choice of emissions data matter?

Compares three tiers of emissions data: static annual (eGRID), hourly average
(AOER), and 5-minute marginal (MOER). Quantifies information lost at each tier
and the cost of using simpler data for scheduling decisions.

Research question:
    "At each tier of emissions data quality, how much scheduling opportunity
    is visible, and what's the cost of using simpler data?"

Outputs:
    Figures:
        fig_ext_three_tier_ladder.png/pdf     — eGRID vs AOER vs MOER by region
        fig_ext_moer_vs_aoer_diurnal.png/pdf  — Overlaid diurnal profiles
        fig_ext_signal_agreement.png/pdf      — % days signals agree on best window
    Tables:
        table_ext_three_tier.csv/md
        table_ext_signal_disagreement.csv/md

Usage:
    python ch3_extended_three_tier_signals.py
    python ch3_extended_three_tier_signals.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, load_hourly, get_run_dir,
    compute_thresholds, simulate_day,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor, rmarker,
    FIGURES_DIR, TABLES_DIR, RUNS_DIR,
    save_cache, load_cache,
)


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

# AOER run folder (separate from MOER run)
AOER_RUN_DIR_NAME = "2026-03-04_AOER_6RegionSummary_V1"

# Mapping: MOER subregion → AOER parent BA → geographic match quality
REGION_MAPPING = {
    "BPA":                {"aoer_ba": "BPA",    "match": "exact",      "egrid_ba": "BPAT"},
    "CAISO_NORTH":        {"aoer_ba": "CAISO",  "match": "good",       "egrid_ba": "CISO"},
    "ERCOT_NORTHCENTRAL": {"aoer_ba": "ERCOT",  "match": "moderate",   "egrid_ba": "ERCO"},
    "ISONE_CT":           {"aoer_ba": "ISONE",  "match": "good",       "egrid_ba": "ISNE"},
    "MISO_INDIANAPOLIS":  {"aoer_ba": "MISO",   "match": "poor",       "egrid_ba": "MISO"},
    "SPP_KANSAS":         {"aoer_ba": "SPP",    "match": "moderate",   "egrid_ba": "SWPP"},
}

# eGRID2023 BA-level annual CO2 output emission rates (lbs CO2/MWh)
# Source: EPA eGRID2023, BA23 sheet, BACO2RTA column
EGRID_BA_RATES = {
    "BPAT": 212.5,    # BPA — mostly hydro
    "CISO": 369.3,    # CAISO — solar + gas
    "ERCO": 734.0,    # ERCOT — gas + wind + coal
    "ISNE": 541.4,    # ISO-NE — gas + nuclear
    "MISO": 982.0,    # MISO — coal + gas + wind
    "SWPP": 871.5,    # SPP — gas + wind + coal
}

# eGRID subregion rates for comparison (SRCO2RTA)
EGRID_SUBREGION_RATES = {
    "NWPP": 631.7,    # WECC Northwest (includes non-BPA)
    "CAMX": 428.5,    # WECC California
    "ERCT": 733.9,    # ERCOT All
    "NEWE": 539.3,    # NPCC New England
    "RFCW": 911.4,    # RFC West (covers Indiana)
    "SPNO": 862.0,    # SPP North (covers Kansas)
}

# Indiana state rate for special comparison
EGRID_INDIANA_STATE = 1457.2  # lbs CO2/MWh (eGRID2023 ST23)


# =============================================================================
# DATA LOADING
# =============================================================================

def load_aoer_hourly():
    """Load AOER hourly data from the AOER run folder."""
    aoer_dir = RUNS_DIR / AOER_RUN_DIR_NAME
    if not aoer_dir.exists():
        print(f"  ⚠️ AOER run folder not found: {aoer_dir}")
        return None
    path = aoer_dir / "processed" / "data_hourly.parquet"
    if not path.exists():
        print(f"  ⚠️ AOER hourly data not found")
        return None
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    print(f"  Loaded AOER hourly: {len(df):,} records, regions: {df['region'].unique().tolist()}")
    return df


# =============================================================================
# ANALYSIS 1 — THREE-TIER LADDER
# =============================================================================

def compute_three_tier_comparison(df_moer_5min, df_aoer_hourly):
    """
    Compare eGRID static, AOER mean, and MOER mean for manufacturing hours.
    """
    print("\n── Three-tier emissions ladder ──")

    rows = []
    for moer_region, mapping in REGION_MAPPING.items():
        aoer_ba = mapping["aoer_ba"]
        egrid_ba = mapping["egrid_ba"]

        # MOER: mean during manufacturing hours
        moer_data = df_moer_5min[
            (df_moer_5min["region"] == moer_region)
            & (df_moer_5min["hour"] >= DAY_SHIFT_START)
            & (df_moer_5min["hour"] < DAY_SHIFT_END)
        ]
        moer_mean = moer_data["value"].mean() if len(moer_data) > 0 else np.nan
        moer_daily_range = moer_data.groupby("date")["value"].apply(
            lambda x: x.max() - x.min()
        ).mean() if len(moer_data) > 0 else np.nan

        # AOER: mean during manufacturing hours
        aoer_mean = np.nan
        aoer_daily_range = np.nan
        if df_aoer_hourly is not None:
            aoer_data = df_aoer_hourly[
                (df_aoer_hourly["region"] == aoer_ba)
                & (df_aoer_hourly["hour"] >= DAY_SHIFT_START)
                & (df_aoer_hourly["hour"] < DAY_SHIFT_END)
            ]
            if len(aoer_data) > 0:
                aoer_mean = aoer_data["value_mean"].mean()
                aoer_daily_range = aoer_data.groupby("date")["value_mean"].apply(
                    lambda x: x.max() - x.min()
                ).mean()

        # eGRID: static annual
        egrid_rate = EGRID_BA_RATES.get(egrid_ba, np.nan)

        # eGRID error vs actual manufacturing-hours MOER
        egrid_error_pct = (egrid_rate - moer_mean) / moer_mean * 100 if moer_mean > 0 else np.nan

        rows.append({
            "moer_region": moer_region,
            "aoer_ba": aoer_ba,
            "match_quality": mapping["match"],
            "egrid_rate": egrid_rate,
            "aoer_mfg_mean": aoer_mean,
            "moer_mfg_mean": moer_mean,
            "egrid_vs_moer_pct": egrid_error_pct,
            "aoer_daily_range": aoer_daily_range,
            "moer_daily_range": moer_daily_range,
            "range_ratio": aoer_daily_range / moer_daily_range if moer_daily_range > 0 else np.nan,
        })

        record_number("Three-tier", f"{rshort(moer_region)} eGRID rate", egrid_rate, ".0f")
        record_number("Three-tier", f"{rshort(moer_region)} MOER mfg-hours mean", moer_mean, ".0f")
        if not np.isnan(aoer_mean):
            record_number("Three-tier", f"{rshort(moer_region)} AOER mfg-hours mean", aoer_mean, ".0f")
        record_number("Three-tier", f"{rshort(moer_region)} eGRID error vs MOER %", egrid_error_pct, ".1f")

    # Special: Indiana state rate
    miso_moer = [r for r in rows if r["moer_region"] == "MISO_INDIANAPOLIS"]
    if miso_moer:
        indy_err = (EGRID_INDIANA_STATE - miso_moer[0]["moer_mfg_mean"]) / miso_moer[0]["moer_mfg_mean"] * 100
        record_number("Three-tier", "Indiana STATE eGRID error vs MOER %", indy_err, ".1f")

    table = pd.DataFrame(rows)
    save_table(table, "table_ext_three_tier",
               "Three-tier emissions data comparison: eGRID vs AOER vs MOER.")
    return table


def plot_three_tier_ladder(tier_table):
    """Grouped bar: eGRID vs AOER vs MOER by region."""
    print("\n── Fig: Three-tier ladder ──")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 5))
        regions = list(CH3_REGIONS.keys())
        tier_table = tier_table.set_index("moer_region").reindex(regions)
        x = np.arange(len(regions))
        w = 0.25

        ax.bar(x - w, tier_table["egrid_rate"], w, label="eGRID (static annual)",
               color="#d73027", edgecolor="white", alpha=0.85)
        aoer_vals = tier_table["aoer_mfg_mean"].fillna(0)
        ax.bar(x, aoer_vals, w, label="AOER (hourly average)",
               color="#fc8d59", edgecolor="white", alpha=0.85)
        ax.bar(x + w, tier_table["moer_mfg_mean"], w, label="MOER (5-min marginal)",
               color="#4575b4", edgecolor="white", alpha=0.85)

        ax.set_xticks(x)
        ax.set_xticklabels([rshort(r) for r in regions], fontsize=10)
        ax.set_ylabel(f"CO₂ Rate ({SIGNAL_UNIT})")
        ax.legend(fontsize=9)
        ax.set_ylim(bottom=0)

        # Annotate match quality
        for i, region in enumerate(regions):
            match = REGION_MAPPING[region]["match"]
            if match != "exact":
                ax.text(i, -30, f"({match})", ha="center", fontsize=7, color="gray")

        save_fig(fig, "fig_ext_three_tier_ladder")


# =============================================================================
# ANALYSIS 2 — MOER vs AOER DIURNAL PROFILES
# =============================================================================

def plot_moer_vs_aoer_diurnal(df_moer_5min, df_aoer_hourly):
    """2×3 faceted: MOER vs AOER diurnal profiles overlaid."""
    print("\n── Fig: MOER vs AOER diurnal profiles ──")

    if df_aoer_hourly is None:
        print("  ⚠️ No AOER data — skipping diurnal comparison")
        return

    with thesis_style():
        fig, axes = plt.subplots(2, 3, figsize=(14, 8), sharey=False)
        axes = axes.flatten()

        for i, (moer_region, mapping) in enumerate(REGION_MAPPING.items()):
            ax = axes[i]
            aoer_ba = mapping["aoer_ba"]

            # MOER hourly mean (aggregate from 5-min)
            moer_data = df_moer_5min[df_moer_5min["region"] == moer_region]
            moer_hourly = moer_data.groupby("hour")["value"].mean()

            # AOER hourly mean
            aoer_data = df_aoer_hourly[df_aoer_hourly["region"] == aoer_ba]
            aoer_hourly = aoer_data.groupby("hour")["value_mean"].mean()

            # Plot
            ax.plot(moer_hourly.index, moer_hourly.values,
                    color="#4575b4", linewidth=2, label="MOER (marginal)")
            if len(aoer_hourly) > 0:
                ax.plot(aoer_hourly.index, aoer_hourly.values,
                        color="#fc8d59", linewidth=2, linestyle="--", label="AOER (average)")

            # Shade operating window
            ax.axvspan(DAY_SHIFT_START, DAY_SHIFT_END, alpha=0.05, color="green")
            ax.set_title(f"{rshort(moer_region)} ({mapping['match']})", fontsize=10)
            ax.set_xlim(0, 23)
            ax.set_xticks(range(0, 24, 6))
            if i >= 3:
                ax.set_xlabel("Hour of Day")
            if i % 3 == 0:
                ax.set_ylabel(f"{SIGNAL_UNIT}")
            if i == 0:
                ax.legend(fontsize=8)

        plt.tight_layout()
        save_fig(fig, "fig_ext_moer_vs_aoer_diurnal")


# =============================================================================
# ANALYSIS 3 — SCHEDULING RECOMMENDATION AGREEMENT
# =============================================================================

def compute_recommendation_agreement(df_moer_5min, df_aoer_hourly):
    """
    For each day, compare which 2-hour window MOER and AOER recommend.
    Report agreement rate and wrong-signal penalty.
    """
    print("\n── Scheduling recommendation agreement ──")

    if df_aoer_hourly is None:
        print("  ⚠️ No AOER data — skipping agreement analysis")
        return pd.DataFrame()

    rows = []
    for moer_region, mapping in REGION_MAPPING.items():
        aoer_ba = mapping["aoer_ba"]

        # Get MOER and AOER data for operating window
        moer_data = df_moer_5min[
            (df_moer_5min["region"] == moer_region)
            & (df_moer_5min["hour"] >= DAY_SHIFT_START)
            & (df_moer_5min["hour"] < DAY_SHIFT_END)
        ]
        aoer_data = df_aoer_hourly[
            (df_aoer_hourly["region"] == aoer_ba)
            & (df_aoer_hourly["hour"] >= DAY_SHIFT_START)
            & (df_aoer_hourly["hour"] < DAY_SHIFT_END)
        ]

        if len(aoer_data) == 0:
            continue

        # Find overlapping dates
        moer_dates = set(moer_data["date"].unique())
        aoer_dates = set(aoer_data["date"].unique())
        common_dates = sorted(moer_dates & aoer_dates)

        for date in common_dates:
            # MOER: best 2-consecutive-hour start (from 5-min, aggregated)
            md = moer_data[moer_data["date"] == date]
            moer_hourly_means = md.groupby("hour")["value"].mean()
            if len(moer_hourly_means) < 3:
                continue
            hours = sorted(moer_hourly_means.index)
            best_moer_start = None
            best_moer_val = np.inf
            for h in hours:
                if h + 1 in moer_hourly_means.index:
                    avg = (moer_hourly_means[h] + moer_hourly_means[h + 1]) / 2
                    if avg < best_moer_val:
                        best_moer_val = avg
                        best_moer_start = h

            # AOER: best 2-consecutive-hour start
            ad = aoer_data[aoer_data["date"] == date]
            aoer_hourly_means = ad.set_index("hour")["value_mean"]
            if len(aoer_hourly_means) < 3:
                continue
            a_hours = sorted(aoer_hourly_means.index)
            best_aoer_start = None
            best_aoer_val = np.inf
            for h in a_hours:
                if h + 1 in aoer_hourly_means.index:
                    avg = (aoer_hourly_means[h] + aoer_hourly_means[h + 1]) / 2
                    if avg < best_aoer_val:
                        best_aoer_val = avg
                        best_aoer_start = h

            if best_moer_start is None or best_aoer_start is None:
                continue

            # Agreement: same start ±1 hour
            agrees = abs(best_moer_start - best_aoer_start) <= 1

            # Wrong-signal penalty: actual MOER at AOER-recommended vs MOER-recommended window
            if best_aoer_start in moer_hourly_means.index and best_aoer_start + 1 in moer_hourly_means.index:
                moer_at_aoer_rec = (moer_hourly_means[best_aoer_start] + moer_hourly_means[best_aoer_start + 1]) / 2
            else:
                moer_at_aoer_rec = best_moer_val

            penalty = moer_at_aoer_rec - best_moer_val  # lbs/MWh higher if following AOER

            rows.append({
                "moer_region": moer_region,
                "date": date,
                "moer_best_hour": best_moer_start,
                "aoer_best_hour": best_aoer_start,
                "agrees": agrees,
                "moer_at_moer_rec": best_moer_val,
                "moer_at_aoer_rec": moer_at_aoer_rec,
                "wrong_signal_penalty": penalty,
            })

    df = pd.DataFrame(rows)
    if len(df) == 0:
        return df

    # Summary
    for moer_region in REGION_MAPPING:
        rd = df[df["moer_region"] == moer_region]
        if len(rd) == 0:
            continue
        agreement = rd["agrees"].mean() * 100
        mean_penalty = rd["wrong_signal_penalty"].mean()
        record_number("Three-tier", f"{rshort(moer_region)} MOER-AOER agreement %", agreement, ".0f")
        record_number("Three-tier", f"{rshort(moer_region)} wrong-signal penalty (lbs/MWh)", mean_penalty, ".1f")

    save_table(df.groupby("moer_region").agg({
        "agrees": "mean",
        "wrong_signal_penalty": ["mean", "median"],
    }).round(2).reset_index(), "table_ext_signal_disagreement",
               "MOER vs AOER scheduling recommendation agreement.")
    return df


def plot_signal_agreement(agree_df):
    """Bar chart: % agreement and mean penalty by region."""
    print("\n── Fig: Signal agreement ──")

    if len(agree_df) == 0:
        print("  ⚠️ No agreement data to plot")
        return

    summary = agree_df.groupby("moer_region").agg(
        agreement_pct=("agrees", lambda x: x.mean() * 100),
        mean_penalty=("wrong_signal_penalty", "mean"),
    ).reindex(CH3_REGIONS.keys())

    with thesis_style():
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        regions = list(CH3_REGIONS.keys())
        x = np.arange(len(regions))

        # Left: agreement %
        bars = ax1.bar(x, summary["agreement_pct"].values,
                       color=[rcolor(r) for r in regions], edgecolor="white")
        ax1.set_xticks(x)
        ax1.set_xticklabels([rshort(r) for r in regions], fontsize=9)
        ax1.set_ylabel("% Days Agreeing on Best Window (±1hr)")
        ax1.set_ylim(0, 100)
        ax1.axhline(50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

        # Annotate match quality
        for i, region in enumerate(regions):
            match = REGION_MAPPING[region]["match"]
            ax1.text(i, 3, match, ha="center", fontsize=7, color="white", fontweight="bold")

        # Right: wrong-signal penalty
        ax2.bar(x, summary["mean_penalty"].values,
                color=[rcolor(r) for r in regions], edgecolor="white")
        ax2.set_xticks(x)
        ax2.set_xticklabels([rshort(r) for r in regions], fontsize=9)
        ax2.set_ylabel(f"Mean Wrong-Signal Penalty ({SIGNAL_UNIT})")
        ax2.set_ylim(bottom=0)

        plt.tight_layout()
        save_fig(fig, "fig_ext_signal_agreement")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df_moer_5min = load_5min()
    df_aoer_hourly = load_aoer_hourly()

    # Three-tier ladder
    tier_table = compute_three_tier_comparison(df_moer_5min, df_aoer_hourly)
    plot_three_tier_ladder(tier_table)

    # Diurnal profiles
    plot_moer_vs_aoer_diurnal(df_moer_5min, df_aoer_hourly)

    # Recommendation agreement
    agree_df = compute_recommendation_agreement(df_moer_5min, df_aoer_hourly)
    plot_signal_agreement(agree_df)

    export_numbers()
    print("\n✅ Three-tier signal comparison complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
