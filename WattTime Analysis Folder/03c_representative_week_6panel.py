"""
03c_representative_week_6panel.py - Six-Panel Raw Weekly MOER Traces
(renamed from 03.3_representative_week_grid.py per CODE_GUIDE.md's
consolidation guide; logic unchanged)

Shows one representative week of 5-minute MOER data per region.
Day/night shading, P25/P75 threshold lines overlaid.

Usage:
    1. Run 02_data_processing.py first to create a run folder
    2. Edit CONFIG section below
    3. Run: python 03c_representative_week_6panel.py

Output:
    - figures/03_weekly_traces_6panel.png
    - figures/03_weekly_traces_6panel.pdf
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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

# Representative week: set a date string like "2025-07-10" for a fixed week,
# or None to auto-select per region (picks week closest to annual median).
REPRESENTATIVE_WEEK_START = "2024-07-10"  # Week starting July 10, 2025

# If auto-selecting, prefer this year
PREFERRED_YEAR = 2025  # Prefer 2025 data if available

# Column names -- the script prints columns on load so you can verify
# MOER dataset may use different names than AOER; adjust if needed
COL_TIMESTAMP = "point_time_local"
COL_VALUE = "value"
COL_REGION = "region"

FIXED_YLIM = (0, 1600)

# Region keys from the MOER dataset (check df["region"].unique() if these don't match)
PANEL_ORDER = [
    "BPA",
    "CAISO_NORTH",
    "ERCOT_NORTHCENTRAL",
    "ISONE_CT",
    "MISO_INDIANAPOLIS",
    "SPP_KANSAS",
]

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


def load_5min(run_dir: Path) -> pd.DataFrame:
    path = run_dir / "processed" / "data_5min.parquet"
    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} five-minute records")
    print(f"Columns: {list(df.columns)}")
    print(f"Regions: {sorted(df[COL_REGION].unique())}")

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df[COL_TIMESTAMP]):
        df[COL_TIMESTAMP] = pd.to_datetime(df[COL_TIMESTAMP])

    return df


def select_representative_week(df: pd.DataFrame, region: str) -> str:
    """Auto-select a representative 7-day window for a region.
    Uses a rolling approach: tries every possible start date in the data,
    picks the 7-day window whose median is closest to the overall median.
    Works with sparse datasets (even ~60 days).
    """
    rdata = df[df[COL_REGION] == region].copy().sort_values(COL_TIMESTAMP)

    if PREFERRED_YEAR:
        year_data = rdata[rdata[COL_TIMESTAMP].dt.year == PREFERRED_YEAR]
        if len(year_data) > 0:
            rdata = year_data

    overall_median = rdata[COL_VALUE].median()

    # Get unique dates, try each as a potential week start
    rdata["_date"] = rdata[COL_TIMESTAMP].dt.date
    unique_dates = sorted(rdata["_date"].unique())

    best_start = None
    best_dist = float("inf")
    best_median = None
    best_count = 0

    for start_date in unique_dates:
        end_date = pd.Timestamp(start_date) + pd.Timedelta(days=7)
        mask = (rdata[COL_TIMESTAMP] >= pd.Timestamp(start_date)) & \
               (rdata[COL_TIMESTAMP] < end_date)
        chunk = rdata[mask]

        if len(chunk) < 200:  # need at least ~1.5 days of 5-min data
            continue

        chunk_median = chunk[COL_VALUE].median()
        dist = abs(chunk_median - overall_median)

        if dist < best_dist:
            best_dist = dist
            best_start = start_date
            best_median = chunk_median
            best_count = len(chunk)

    if best_start is None:
        # Last resort: just use the first date
        best_start = unique_dates[0]
        best_median = overall_median
        best_count = len(rdata)
        print(f"  {region}: WARNING - using first available date {best_start}")
    else:
        print(f"  {region}: week of {best_start} "
              f"(median {best_median:.0f} vs overall {overall_median:.0f}, "
              f"n={best_count})")

    rdata.drop(columns=["_date"], inplace=True)
    return str(best_start)


def add_night_shading(ax, start_date, n_days=7):
    """Night = 18:00 to 06:00 next day."""
    for d in range(n_days + 1):
        evening_start = pd.Timestamp(start_date) + pd.Timedelta(days=d, hours=18)
        evening_end = pd.Timestamp(start_date) + pd.Timedelta(days=d + 1, hours=0)
        ax.axvspan(evening_start, evening_end, alpha=0.08, color="navy", zorder=0)

        morning_start = pd.Timestamp(start_date) + pd.Timedelta(days=d, hours=0)
        morning_end = pd.Timestamp(start_date) + pd.Timedelta(days=d, hours=6)
        ax.axvspan(morning_start, morning_end, alpha=0.08, color="navy", zorder=0)


def add_day_labels(ax, start_date, n_days=7):
    """Day-of-week labels at noon."""
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    start = pd.Timestamp(start_date)
    for d in range(n_days):
        noon = start + pd.Timedelta(days=d, hours=12)
        day_name = days[noon.weekday()]
        ax.text(noon, FIXED_YLIM[1] * 0.95, day_name,
                ha="center", va="top", fontsize=8, alpha=0.5, fontweight="bold")


def plot_grid(df: pd.DataFrame, signal: str, figures_dir: Path):
    """Create 3x2 grid of raw weekly MOER traces."""

    unit_label = get_unit_label(signal)
    signal_meta = get_signal_metadata(signal)

    fig, axes = plt.subplots(3, 2, figsize=(14, 10), sharey=True)
    axes_flat = axes.flatten()

    # Select representative week per region
    week_starts = {}
    print("\nSelecting representative weeks...")
    for region in PANEL_ORDER:
        if REPRESENTATIVE_WEEK_START:
            week_starts[region] = REPRESENTATIVE_WEEK_START
        else:
            week_starts[region] = select_representative_week(df, region)

    for idx, region in enumerate(PANEL_ORDER):
        ax = axes_flat[idx]
        rdata = df[df[COL_REGION] == region].copy()

        if len(rdata) == 0:
            ax.text(0.5, 0.5, f"No data: {region}", transform=ax.transAxes,
                    ha="center", va="center")
            continue

        # Extract the week
        week_start = pd.Timestamp(week_starts[region])
        week_end = week_start + pd.Timedelta(days=7)
        mask = (rdata[COL_TIMESTAMP] >= week_start) & (rdata[COL_TIMESTAMP] < week_end)
        week_data = rdata[mask].sort_values(COL_TIMESTAMP)

        if len(week_data) == 0:
            ax.text(0.5, 0.5, f"No data for week\n{week_start.date()}",
                    transform=ax.transAxes, ha="center", va="center")
            continue

        color = REGION_COLORS.get(region, "#1f77b4")

        # Night shading
        add_night_shading(ax, week_start, n_days=7)

        # Day labels
        add_day_labels(ax, week_start, n_days=7)

        # P25/P75 threshold lines (full-dataset)
        p25 = rdata[COL_VALUE].quantile(0.25)
        p75 = rdata[COL_VALUE].quantile(0.75)
        ax.axhline(y=p25, color="green", linestyle="--", linewidth=1, alpha=0.6, zorder=1)
        ax.axhline(y=p75, color="red", linestyle="--", linewidth=1, alpha=0.6, zorder=1)

        # Green zone shading
        ax.axhspan(0, p25, alpha=0.04, color="green", zorder=0)

        # Raw 5-min trace
        ax.plot(week_data[COL_TIMESTAMP], week_data[COL_VALUE],
                color=color, linewidth=0.5, alpha=0.8, zorder=2)

        # Panel label
        region_name = REGIONS.get(region, {}).get("name", region)
        archetype = ARCHETYPE_LABELS.get(region, "")
        ax.set_title(f"{region_name} ({archetype})", fontsize=10, fontweight="bold")

        ax.set_xlim(week_start, week_end)
        ax.set_ylim(FIXED_YLIM)
        ax.grid(True, alpha=0.2)

        # X-axis formatting
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.tick_params(axis="x", labelsize=8, rotation=0)

    # Shared axis labels
    for ax in axes[-1, :]:
        ax.set_xlabel("Date", fontsize=10)
    for ax in axes[:, 0]:
        ax.set_ylabel(f"{signal_meta['name']}\n({unit_label})", fontsize=9)

    # --- Suptitle (commented out) ---
    # fig.suptitle("Representative Week: 5-Minute MOER Traces by Region",
    #              fontsize=13, fontweight="bold")

    # --- Legend (commented out) ---
    # from matplotlib.lines import Line2D
    # legend_elements = [
    #     Line2D([0], [0], color="gray", linewidth=0.8, label="5-min MOER"),
    #     Line2D([0], [0], color="green", linewidth=1, linestyle="--", label="P25 (green threshold)"),
    #     Line2D([0], [0], color="red", linewidth=1, linestyle="--", label="P75 (red threshold)"),
    # ]
    # fig.legend(handles=legend_elements, loc="lower center", ncol=3,
    #            fontsize=9, frameon=True, bbox_to_anchor=(0.5, -0.01))

    plt.tight_layout()

    for ext in ["png", "pdf"]:
        outpath = figures_dir / f"03_weekly_traces_6panel.{ext}"
        fig.savefig(outpath, dpi=FIGURE_DPI, bbox_inches="tight")
        print(f"Saved: {outpath}")

    plt.close()


def main():
    run_dir = get_run_dir()
    with open(run_dir / "run_config.json", "r") as f:
        config = json.load(f)
    signal = config["signal"]

    print("=" * 60)
    print("REPRESENTATIVE WEEK GRID FIGURE (6 panels)")
    print(f"Run: {run_dir.name}  |  Signal: {signal}")
    print("=" * 60)

    df = load_5min(run_dir)

    figures_dir = run_dir / "figures"
    figures_dir.mkdir(exist_ok=True)

    plot_grid(df, signal, figures_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()