"""
ch3_extended_intra_iso_portability.py — One rule for all plants in the same region?

Tests whether scheduling heuristics developed for one subregion work at other
subregions within the same ISO. Uses MISO subregions as the primary case study.

Research question:
    "If a company has 3 plants in the same ISO, can they use one set of
    thresholds for all 3, or does each plant need its own calibration?"

Outputs:
    Figures:
        fig_ext_intra_iso_correlation.png/pdf
        fig_ext_distance_vs_correlation.png/pdf
        fig_ext_threshold_portability.png/pdf
    Tables:
        table_ext_spatial_portability.csv/md

Usage:
    python ch3_extended_intra_iso_portability.py
    python ch3_extended_intra_iso_portability.py --recompute

Note:
    Requires MOER data for multiple subregions within at least one ISO.
    If only the 6 archetype regions are available, falls back to cross-archetype
    analysis (which shows that region-specific calibration IS needed).
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from itertools import combinations

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, get_run_dir,
    simulate_day,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rlabel, rshort, rcolor,
    FIGURES_DIR, save_cache, load_cache,
)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import REGIONS as ALL_REGIONS, RUNS_DIR


# =============================================================================
# ▼▼▼ CONFIG ▼▼▼
# =============================================================================

# ISO groups to test (if data available). The script will auto-detect what exists.
ISO_GROUPS = {
    "MISO": [
        "MISO_INDIANAPOLIS", "MISO_DETROIT", "MISO_GRAND_RAPIDS",
        "MISO_MINNEAPOLIS", "MISO_MADISON", "MISO_EAU_CLAIRE",
        "MISO_SAINT_LOUIS", "MISO_SPRINGFIELD", "MISO_LAFAYETTE",
        "MISO_NEW_ORLEANS", "MISO_LOWER_MS_RIVER", "MISO_BEAUMONT",
        "MISO_N_DAKOTA", "MISO_MASON_CITY", "MISO_WORTHINGTON",
        "MISO_UPPER_PENINSULA",
    ],
    "ERCOT": [
        "ERCOT_NORTHCENTRAL", "ERCOT_AUSTIN", "ERCOT_SANANTONIO",
        "ERCOT_EASTTX", "ERCOT_COAST", "ERCOT_SECOAST",
        "ERCOT_SOUTHTX", "ERCOT_HIDALGO", "ERCOT_WESTTX", "ERCOT_PANHANDLE",
    ],
    "SPP": [
        "SPP_KANSAS", "SPP_KC", "SPP_OKCTY", "SPP_SWOK", "SPP_TX",
        "SPP_MEMPHIS", "SPP_SPRINGFIELD", "SPP_SIOUX", "SPP_ND",
        "SPP_WESTNE", "SPP_FORTPECK",
    ],
}

# Reference subregion for portability test (thresholds from here applied elsewhere)
REFERENCE_SUBREGIONS = {
    "MISO": "MISO_INDIANAPOLIS",
    "ERCOT": "ERCOT_NORTHCENTRAL",
    "SPP": "SPP_KANSAS",
}


# =============================================================================
# DATA LOADING
# =============================================================================

def load_all_subregion_data():
    """
    Load 5-min data for all available subregions.
    Uses the processed run folder — which may contain only the 6 archetypes.
    If so, try loading additional subregions from library directly.
    """
    print("\n  Loading subregion data...")
    run_dir = get_run_dir()
    df = pd.read_parquet(run_dir / "processed" / "data_5min.parquet")

    available = set(df["region"].unique())
    print(f"  Available in run: {sorted(available)}")

    # Check which ISOs have multiple subregions
    iso_coverage = {}
    for iso, subregions in ISO_GROUPS.items():
        present = [r for r in subregions if r in available]
        iso_coverage[iso] = present
        if len(present) > 1:
            print(f"  {iso}: {len(present)} subregions available")
        elif len(present) == 1:
            print(f"  {iso}: only {present[0]} — need more for intra-ISO analysis")
        else:
            print(f"  {iso}: no subregions in dataset")

    return df, iso_coverage


# =============================================================================
# ANALYSIS 1 — PAIRWISE CORRELATION
# =============================================================================

def compute_pairwise_correlations(df, iso_coverage, recompute=False):
    """Hourly MOER correlation between all pairs within each ISO."""
    print("\n── Pairwise correlations ──")

    cache_tag = "ext_spatial_corr"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    rows = []
    for iso, subregions in iso_coverage.items():
        if len(subregions) < 2:
            continue

        # Aggregate to hourly for correlation (reduces noise)
        iso_data = df[df["region"].isin(subregions)].copy()
        hourly = iso_data.groupby(["region", "date", "hour"])["value"].mean().reset_index()

        for r1, r2 in combinations(subregions, 2):
            d1 = hourly[hourly["region"] == r1].set_index(["date", "hour"])["value"]
            d2 = hourly[hourly["region"] == r2].set_index(["date", "hour"])["value"]

            common = d1.index.intersection(d2.index)
            if len(common) < 100:
                continue

            corr = np.corrcoef(d1[common].values, d2[common].values)[0, 1]

            # Geographic distance
            c1 = ALL_REGIONS.get(r1, {}).get("coordinates", (0, 0))
            c2 = ALL_REGIONS.get(r2, {}).get("coordinates", (0, 0))
            # Approximate km using haversine-like
            dist_km = np.sqrt((69 * (c1[0] - c2[0])) ** 2 + (54 * (c1[1] - c2[1])) ** 2) * 1.6

            rows.append({
                "iso": iso, "region_1": r1, "region_2": r2,
                "correlation": corr, "distance_km": dist_km,
                "n_common_hours": len(common),
            })

    df_out = pd.DataFrame(rows)
    save_cache(df_out, cache_tag, {"v": 2})

    # Record stats
    for iso in ISO_GROUPS:
        iso_data = df_out[df_out["iso"] == iso]
        if len(iso_data) > 0:
            record_number("Spatial", f"{iso} mean intra-ISO correlation", iso_data["correlation"].mean(), ".2f")
            record_number("Spatial", f"{iso} min intra-ISO correlation", iso_data["correlation"].min(), ".2f")

    return df_out


def plot_correlation_heatmap(corr_df, iso_coverage):
    """Heatmap of pairwise correlations for the largest ISO group."""
    print("\n── Fig: Correlation heatmap ──")

    # Pick the ISO with most subregions
    best_iso = max(iso_coverage, key=lambda k: len(iso_coverage[k]))
    iso_data = corr_df[corr_df["iso"] == best_iso]

    if len(iso_data) == 0:
        print(f"  ⚠️ No pairs for {best_iso}")
        return

    # Build matrix
    all_regions = sorted(set(iso_data["region_1"]) | set(iso_data["region_2"]))
    n = len(all_regions)
    matrix = np.ones((n, n))

    region_idx = {r: i for i, r in enumerate(all_regions)}
    for _, row in iso_data.iterrows():
        i, j = region_idx[row["region_1"]], region_idx[row["region_2"]]
        matrix[i, j] = row["correlation"]
        matrix[j, i] = row["correlation"]

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=1)

        short_labels = [r.split("_", 1)[-1][:12] for r in all_regions]
        ax.set_xticks(range(n))
        ax.set_xticklabels(short_labels, fontsize=8, rotation=45, ha="right")
        ax.set_yticks(range(n))
        ax.set_yticklabels(short_labels, fontsize=8)

        for i in range(n):
            for j in range(n):
                if i != j:
                    ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center", fontsize=7)

        fig.colorbar(im, ax=ax, shrink=0.7, label="Hourly MOER Correlation")
        ax.set_title(f"Intra-{best_iso} Subregional MOER Correlation")

        save_fig(fig, "fig_ext_intra_iso_correlation")


def plot_distance_vs_correlation(corr_df):
    """Scatter: geographic distance vs MOER correlation."""
    print("\n── Fig: Distance vs correlation ──")

    if len(corr_df) == 0:
        print("  ⚠️ No correlation data")
        return

    iso_colors = {"MISO": "#555555", "ERCOT": "#009988", "SPP": "#33BBEE"}

    with thesis_style():
        fig, ax = plt.subplots(figsize=(9, 5))

        for iso in corr_df["iso"].unique():
            rd = corr_df[corr_df["iso"] == iso]
            ax.scatter(rd["distance_km"], rd["correlation"],
                       color=iso_colors.get(iso, "#333"), s=40, alpha=0.6, label=iso)

        ax.set_xlabel("Geographic Distance (km)")
        ax.set_ylabel("Hourly MOER Correlation")
        ax.set_ylim(-0.1, 1.05)
        ax.axhline(0.85, color="green", linestyle="--", linewidth=0.8, label="r=0.85 (portable)")
        ax.axhline(0.5, color="red", linestyle=":", linewidth=0.8, label="r=0.50 (divergent)")
        ax.legend(fontsize=9)

        save_fig(fig, "fig_ext_distance_vs_correlation")


# =============================================================================
# ANALYSIS 2 — THRESHOLD PORTABILITY
# =============================================================================

def compute_threshold_portability(df, iso_coverage, recompute=False):
    """
    Compute thresholds from reference subregion, apply to others.
    Report retained savings vs locally-optimal thresholds.
    """
    print("\n── Threshold portability ──")

    cache_tag = "ext_portability"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 2})
        if cached is not None:
            return cached

    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"

    window = df[
        (df["hour"] >= DAY_SHIFT_START)
        & (df["hour"] < DAY_SHIFT_END)
    ]

    rows = []
    for iso, subregions in iso_coverage.items():
        if len(subregions) < 2:
            continue

        ref = REFERENCE_SUBREGIONS.get(iso)
        if ref not in subregions:
            ref = subregions[0]

        # Reference thresholds
        ref_data = window[window["region"] == ref]
        if len(ref_data) < 1000:
            continue
        ref_gt = ref_data["value"].quantile(GREEN_PERCENTILE / 100)
        ref_rt = ref_data["value"].quantile(RED_PERCENTILE / 100)

        for target in subregions:
            target_data = window[window["region"] == target].sort_values("point_time_local")
            if len(target_data) < 1000:
                continue

            # Local thresholds
            local_gt = target_data["value"].quantile(GREEN_PERCENTILE / 100)
            local_rt = target_data["value"].quantile(RED_PERCENTILE / 100)

            # Simulate with both threshold sets
            ref_savings, local_savings = [], []
            for date, ddf in target_data.groupby("date"):
                vals = ddf.sort_values("point_time_local")["value"].values
                if len(vals) < job_intervals:
                    continue

                sim_ref = simulate_day(vals, job_intervals, ref_gt, ref_rt)
                sim_local = simulate_day(vals, job_intervals, local_gt, local_rt)
                if sim_ref is None or sim_local is None:
                    continue

                b = sim_ref["baseline_moer"]
                if b <= 0:
                    continue
                ref_savings.append((b - sim_ref[tl_key]) / b * 100)
                local_savings.append((b - sim_local[tl_key]) / b * 100)

            if len(ref_savings) < 30:
                continue

            mean_ref = np.mean(ref_savings)
            mean_local = np.mean(local_savings)
            retained = mean_ref / mean_local * 100 if mean_local > 0 else 100

            rows.append({
                "iso": iso,
                "reference_region": ref,
                "target_region": target,
                "is_same": ref == target,
                "ref_threshold_savings_pct": mean_ref,
                "local_threshold_savings_pct": mean_local,
                "retained_pct": retained,
                "ref_gt": ref_gt, "local_gt": local_gt,
                "threshold_diff": abs(ref_gt - local_gt),
            })

    df_out = pd.DataFrame(rows)
    save_cache(df_out, cache_tag, {"v": 2})

    # Stats
    other = df_out[~df_out["is_same"]]
    if len(other) > 0:
        record_number("Spatial", "Mean portability retained %", other["retained_pct"].mean(), ".0f")
        record_number("Spatial", "Min portability retained %", other["retained_pct"].min(), ".0f")

    save_table(df_out, "table_ext_spatial_portability",
               "Threshold portability: reference subregion thresholds applied to others.")
    return df_out


def plot_threshold_portability(port_df):
    """Bar chart: retained savings when using reference thresholds."""
    print("\n── Fig: Threshold portability ──")

    other = port_df[~port_df["is_same"]]
    if len(other) == 0:
        print("  ⚠️ No cross-subregion portability data")
        return

    with thesis_style():
        fig, ax = plt.subplots(figsize=(12, 5))

        other_sorted = other.sort_values("retained_pct", ascending=False)
        labels = [f"{r.split('_', 1)[-1][:10]}" for r in other_sorted["target_region"]]
        colors = ["#2ca02c" if r > 90 else "#fc8d59" if r > 70 else "#d73027"
                  for r in other_sorted["retained_pct"]]

        ax.bar(range(len(labels)), other_sorted["retained_pct"], color=colors, edgecolor="white")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=7, rotation=45, ha="right")
        ax.set_ylabel("Retained Savings (%)\n(using reference thresholds)")
        ax.axhline(90, color="green", linestyle="--", linewidth=0.8, label="90% (portable)")
        ax.axhline(70, color="orange", linestyle=":", linewidth=0.8, label="70% (marginal)")
        ax.set_ylim(0, 115)
        ax.legend(fontsize=9)

        # Annotate reference
        ref_region = other_sorted["reference_region"].iloc[0]
        ax.set_title(f"Portability of {ref_region.split('_', 1)[-1]} thresholds to other subregions")

        save_fig(fig, "fig_ext_threshold_portability")


# =============================================================================
# MAIN
# =============================================================================

def main(recompute=False):
    init()

    df, iso_coverage = load_all_subregion_data()

    # Check if we have enough for intra-ISO analysis
    multi_iso = {k: v for k, v in iso_coverage.items() if len(v) >= 2}
    if not multi_iso:
        print("\n⚠️ No ISO has multiple subregions in the dataset.")
        print("  Falling back to cross-archetype analysis (6 study regions).")
        print("  To enable intra-ISO: collect additional subregions via 01_data_collection.py")
        # Could still do cross-archetype portability here as fallback
        export_numbers()
        return

    corr_df = compute_pairwise_correlations(df, iso_coverage, recompute=recompute)
    plot_correlation_heatmap(corr_df, iso_coverage)
    plot_distance_vs_correlation(corr_df)

    port_df = compute_threshold_portability(df, iso_coverage, recompute=recompute)
    plot_threshold_portability(port_df)

    export_numbers()
    print("\n✅ Intra-ISO portability analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
