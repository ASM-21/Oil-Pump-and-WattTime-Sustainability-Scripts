"""
03.2_temporal_patterns_gridfigure.py - Six-Panel Diurnal MOER Profile Grid

Creates a single figure with all six regions as subplots.
Each panel: median (solid) + mean (dashed), P25-P75 and P10-P90 bands.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit RUN_FOLDER below
    3. Run: python 03.2_temporal_patterns_gridfigure.py

Output:
    - figures/03_diurnal_grid_6panel.png
    - figures/03_diurnal_grid_6panel.pdf
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, RUNS_DIR,
    FIGURE_DPI, REGION_COLORS,
    get_signal_metadata, get_unit_label
)

# =============================================================================
# CONFIG
# =============================================================================

RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"

FIXED_YLIM = (0, 1600)

# Panel order matches Table 3-1
PANEL_ORDER = [
    "BPA",
    "CAISO_NORTH",
    "ERCOT_NORTHCENTRAL",
    "ISONE_CT",
    "MISO_INDIANAPOLIS",
    "SPP_KANSAS",
]

# Archetype labels for subtitles (matches Table 3-1)
ARCHETYPE_LABELS = {
    "BPA": "Hydro-baseload",
    "CAISO_NORTH": "Solar-dominated",
    "ERCOT_NORTHCENTRAL": "Wind-gas mix",
    "ISONE_CT": "Nuclear-gas mix",
    "MISO_INDIANAPOLIS": "Fossil-heavy",
    "SPP_KANSAS": "Wind-dominated",
}

# =============================================================================


def get_run_dir() -> Path:
    run_dir = RUNS_DIR / RUN_FOLDER
    if not run_dir.exists():
        print(f"ERROR: Run folder not found: {run_dir}")
        sys.exit(1)
    return run_dir


def load_hourly(run_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(run_dir / "processed" / "data_hourly.parquet")
    print(f"Loaded {len(df):,} hourly records")
    return df


def plot_grid(df_hourly: pd.DataFrame, signal: str, figures_dir: Path):
    """Create 3x2 grid of diurnal profiles."""

    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)

    fig, axes = plt.subplots(3, 2, figsize=(12, 12), sharex=True, sharey=True)
    axes_flat = axes.flatten()

    for idx, region in enumerate(PANEL_ORDER):
        ax = axes_flat[idx]
        data = df_hourly[df_hourly["region"] == region]

        if len(data) == 0:
            ax.text(0.5, 0.5, f"No data: {region}", transform=ax.transAxes,
                    ha="center", va="center")
            continue

        # Aggregate by hour
        stats = data.groupby("hour").agg(
            mean=("value_mean", "mean"),
            median=("value_mean", "median"),
            p10=("value_mean", lambda x: x.quantile(0.10)),
            p25=("value_mean", lambda x: x.quantile(0.25)),
            p75=("value_mean", lambda x: x.quantile(0.75)),
            p90=("value_mean", lambda x: x.quantile(0.90)),
        ).reset_index()

        h = stats["hour"]
        color = REGION_COLORS.get(region, "#1f77b4")

        # P10-P90 band (wider, lighter)
        ax.fill_between(h, stats["p10"], stats["p90"],
                        alpha=0.15, color=color, zorder=0)

        # P25-P75 band (IQR, darker)
        ax.fill_between(h, stats["p25"], stats["p75"],
                        alpha=0.4, color=color, zorder=1)

        # Mean (dashed)
        ax.plot(h, stats["mean"], color=color, linewidth=1.5,
                linestyle="--", alpha=0.6, zorder=2)

        # Median (solid, primary)
        ax.plot(h, stats["median"], color=color, linewidth=2.5, zorder=3)

        # Shift boundaries
        for sh in [6, 14, 22]:
            ax.axvline(x=sh, color="gray", linestyle="--", alpha=0.4, linewidth=0.8)

        # Panel title: region name + archetype
        region_name = REGIONS.get(region, {}).get("name", region)
        archetype = ARCHETYPE_LABELS.get(region, "")
        ax.set_title(f"{region_name}\n({archetype})", fontsize=11, fontweight="bold")

        ax.set_xlim(0, 23)
        ax.set_xticks(range(0, 24, 3))
        ax.grid(True, alpha=0.3)

    # Set shared y limits
    if FIXED_YLIM:
        for ax in axes_flat:
            ax.set_ylim(FIXED_YLIM)

    # Shared axis labels
    for ax in axes[-1, :]:
        ax.set_xlabel("Hour of Day (Local Time)", fontsize=11)
    for ax in axes[:, 0]:
        ax.set_ylabel(f"{signal_meta['name']}\n({unit_label})", fontsize=10)

    # Shared legend (one for the whole figure)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color="gray", linewidth=2.5, label="Median"),
        Line2D([0], [0], color="gray", linewidth=1.5, linestyle="--", alpha=0.6, label="Mean"),
        Patch(facecolor="gray", alpha=0.4, label="25th-75th percentile"),
        Patch(facecolor="gray", alpha=0.15, label="10th-90th percentile"),
    ]
  #  fig.legend(handles=legend_elements, loc="lower center", ncol=4,
   #            fontsize=10, frameon=True, bbox_to_anchor=(0.5, -0.01))

   # fig.suptitle("Diurnal MOER Profiles by Region, 2021-2024", fontsize=14, fontweight="bold")
   # plt.tight_layout(rect=[0, 0.03, 1, 0.96])

    # Save both PNG and PDF
    for ext in ["png", "pdf"]:
        outpath = figures_dir / f"03_diurnal_grid_6panel.{ext}"
        fig.savefig(outpath, dpi=FIGURE_DPI, bbox_inches="tight")
        print(f"Saved: {outpath}")

    plt.close()


def main():
    run_dir = get_run_dir()
    config_path = run_dir / "run_config.json"
    with open(config_path, "r") as f:
        config = json.load(f)
    signal = config["signal"]

    print("=" * 60)
    print("DIURNAL PROFILE GRID FIGURE (6 panels)")
    print(f"Run: {run_dir.name}  |  Signal: {signal}")
    print("=" * 60)

    df_hourly = load_hourly(run_dir)

    figures_dir = run_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    plot_grid(df_hourly, signal, figures_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()