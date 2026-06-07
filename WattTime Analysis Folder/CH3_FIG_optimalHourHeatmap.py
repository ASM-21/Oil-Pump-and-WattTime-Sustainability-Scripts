"""
ch3_fig_moer_heatmap_grid.py — Fig 3-X: MOER Heatmap Grid (Hour × Month, All Regions)

2×3 grid, one panel per region. Each panel shows mean MOER as a function of
hour of day (y-axis, 0–23) and month (x-axis, Jan–Dec). Shared colorscale
across all panels so green (low MOER) zones are directly comparable.

The green bands show when scheduling saves the most carbon, and how that
pattern shifts seasonally across grid archetypes.

Output:
    ch3_outputs/figures/fig_moer_heatmap_grid.png/pdf

Usage:
    python ch3_fig_moer_heatmap_grid.py
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from mpl_toolkits.axes_grid1 import make_axes_locatable

from ch3_common import (
    init, thesis_style, save_fig, load_5min,
    CH3_REGIONS, CHARACTERIZATION_YEARS,
    rshort,
)

# =============================================================================
# CONFIG
# =============================================================================
ANALYSIS_YEARS = CHARACTERIZATION_YEARS
FIGSIZE        = (14, 8)
CMAP           = "RdYlGn_r"    # red = high MOER, green = low MOER
LAYOUT         = (2, 3)        # rows × cols
VMIN           = None          # None = auto from data (shared across all panels)
VMAX           = None
MONTH_LABELS   = ["Jan","Feb","Mar","Apr","May","Jun",
                  "Jul","Aug","Sep","Oct","Nov","Dec"]


# =============================================================================
# COMPUTE
# =============================================================================

def compute_pivots(df_hourly: pd.DataFrame) -> dict:
    """
    For each region, build a pivot: rows = hour (0–23), cols = month (1–12),
    values = mean MOER.  Uses the hourly data (value_mean col if present,
    else value).
    """
    val_col = "value_mean" if "value_mean" in df_hourly.columns else "value"

    pivots = {}
    for region in CH3_REGIONS:
        rd = df_hourly[df_hourly["region"] == region]
        if len(rd) == 0:
            pivots[region] = None
            continue
        pivot = (
            rd.groupby(["hour", "month"])[val_col]
            .mean()
            .unstack(level="month")          # cols = months 1..12
            .reindex(index=range(24))        # rows = hours 0..23
            .reindex(columns=range(1, 13))   # cols = months 1..12
        )
        pivots[region] = pivot
    return pivots


def global_range(pivots: dict):
    """Compute shared vmin/vmax across all regions."""
    all_vals = []
    for p in pivots.values():
        if p is not None:
            all_vals.append(p.values.ravel())
    flat = np.concatenate(all_vals)
    flat = flat[~np.isnan(flat)]
    return float(np.percentile(flat, 2)), float(np.percentile(flat, 98))


# =============================================================================
# FIGURE
# =============================================================================

def plot_grid(pivots: dict):
    rows, cols = LAYOUT
    regions    = list(CH3_REGIONS.keys())

    vmin = VMIN
    vmax = VMAX
    if vmin is None or vmax is None:
        vmin, vmax = global_range(pivots)

    # imshow extent: x = months 0.5–12.5, y = hours -0.5–23.5
    # with origin="lower" hour 0 is at the bottom
    extent = [0.5, 12.5, -0.5, 23.5]

    with thesis_style():
        fig, axes = plt.subplots(rows, cols, figsize=FIGSIZE,
                                 sharex=True, sharey=True)
        axes_flat = axes.flatten()

        ims = []
        for idx, region in enumerate(regions):
            ax    = axes_flat[idx]
            pivot = pivots.get(region)

            if pivot is None or pivot.isnull().all().all():
                ax.set_visible(False)
                continue

            # Flip rows so row 0 (hour 0) is at the bottom
            im = ax.imshow(
                pivot.values[::-1],
                cmap=CMAP,
                aspect="auto",
                origin="upper",      # imshow draws row 0 at top; we flipped, so hour 0 ends up bottom
                extent=extent,
                vmin=vmin, vmax=vmax,
                interpolation="nearest",
            )
            ims.append(im)

            # Panel title — thesis archetype names
            ARCHETYPE_LABELS = {
                "BPA":                "Hydro-baseload",
                "CAISO_NORTH":        "Solar-dominated",
                "ERCOT_NORTHCENTRAL": "Wind-gas mix",
                "ISONE_CT":           "Gas-nuclear Mix",
                "MISO_INDIANAPOLIS":  "Fossil-Heavy",
                "SPP_KANSAS":         "Wind-dominated",
            }
            short = rshort(region)
            arch  = ARCHETYPE_LABELS.get(region, CH3_REGIONS[region]["archetype"])
            ax.set_title(f"{short} — {arch}", fontsize=11, fontweight="bold", pad=4)

            # x-axis: months — every panel gets labels, bottom row larger
            ax.set_xticks(range(1, 13))
            ax.set_xticklabels(MONTH_LABELS, fontsize=10, rotation=45, ha="right")

            # y-axis: hours every 3h
            ax.set_yticks(range(0, 24, 3))
            ax.set_yticklabels(
                [f"{h:02d}:00" for h in range(0, 24, 3)],
                fontsize=9,
            )

            # Shift window boundary lines (06:00 and 18:00)
            for h in [6, 18]:
                ax.axhline(h, color="white", linewidth=1.2,
                           linestyle="--", alpha=0.8)

            ax.set_xlim(0.5, 12.5)
            ax.set_ylim(-0.5, 23.5)

        # Tight layout first, then add colorbar
        fig.tight_layout(rect=[0.04, 0.06, 0.88, 1.0], h_pad=1.5, w_pad=0.5)
        cbar_ax = fig.add_axes([0.90, 0.12, 0.02, 0.75])
        cbar = fig.colorbar(ims[0], cax=cbar_ax)
        cbar.set_label("Mean MOER (lbs CO₂/MWh)", fontsize=14, fontweight="bold")
        cbar.ax.tick_params(labelsize=11)

        # Shared axis labels
        fig.text(0.46, 0.01, "Month", ha="center", fontsize=13, fontweight="bold")
        fig.text(0.01, 0.5, "Hour of Day (Local Time)",
                 va="center", rotation="vertical", fontsize=12, fontweight="bold")

        save_fig(fig, "fig_moer_heatmap_grid")


# =============================================================================
# MAIN
# =============================================================================

def main():
    init()
    print("\n── MOER Heatmap Grid (Hour × Month, 6 Regions) ──")

    # Load hourly data — heatmap uses hourly averages, not 5-min
    from ch3_common import load_hourly
    df_hourly = load_hourly()
    if ANALYSIS_YEARS:
        df_hourly = df_hourly[df_hourly["year"].isin(ANALYSIS_YEARS)].copy()
        print(f"  Years: {ANALYSIS_YEARS}")

    print("  Computing pivots...")
    pivots = compute_pivots(df_hourly)

    print("  Plotting...")
    plot_grid(pivots)
    print("\n✅ Done.")


if __name__ == "__main__":
    main()