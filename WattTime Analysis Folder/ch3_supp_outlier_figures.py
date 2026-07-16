"""
ch3_supp_figures.py

Three supplementary figures, all from real WattTime MOER data.

  fig_supp_ercot_trap.png     — Best ERCOT first-green trap found in the dataset
  fig_supp_spp_bimodal.png    — SPP Kansas bimodal distribution (operating window)
  fig_supp_caiso_seasonal.png — CAISO seasonal mean profiles, 06:00–18:00

Usage (from project root):
    python ch3_supp_figures.py
    python ch3_supp_figures.py --recompute    # bypass simulation cache
"""

import argparse
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
from pathlib import Path
from scipy.stats import gaussian_kde

# =============================================================================
# MODULE PATCHING — redirect outputs to ch3supp/ before any ch3_common imports
# =============================================================================
sys.path.insert(0, str(Path(__file__).parent))
import ch3_common as _cm

_SUPP_ROOT = Path(__file__).parent / "ch3supp"
_SUPP_ROOT.mkdir(exist_ok=True)
_cm.FIGURES_DIR  = _SUPP_ROOT / "figures"
_cm.TABLES_DIR   = _SUPP_ROOT / "tables"
_cm.CACHE_DIR    = _SUPP_ROOT / "cache"
_cm.NUMBERS_FILE = _SUPP_ROOT / "ch3_numbers_supp_figures.md"
for _d in [_cm.FIGURES_DIR, _cm.TABLES_DIR, _cm.CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

from ch3_common import (
    thesis_style, save_fig, record_number,
    load_5min, compute_thresholds, run_scheduling_sim,
    TRAFFIC_LIGHT_COLORS, SEASON_COLORS, SEASON_ORDER,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
)

GC = TRAFFIC_LIGHT_COLORS["green"]
YC = TRAFFIC_LIGHT_COLORS["yellow"]
RC = TRAFFIC_LIGHT_COLORS["red"]


# =============================================================================
# FIG 1 — ERCOT FIRST-GREEN TRAP
# =============================================================================

def find_ercot_trap_date(sim_df: pd.DataFrame) -> pd.Timestamp:
    """
    Return the ERCOT day with the most negative first-green savings —
    the clearest example of the heuristic backfiring in the dataset.
    """
    ercot = sim_df[
        (sim_df["region"] == "ERCOT_NORTHCENTRAL") &
        (sim_df["savings_fg_pct"] < 0)
    ].sort_values("savings_fg_pct")

    if len(ercot) == 0:
        raise ValueError(
            "No negative first-green days found for ERCOT_NORTHCENTRAL. "
            "Try --recompute or check the run dir."
        )

    best = ercot.iloc[0]
    date = pd.Timestamp(best["date"])
    pct  = best["savings_fg_pct"]
    print(f"  ERCOT trap date: {date.date()}  (savings_fg = {pct:.1f}%)")
    record_number("ERCOT Trap", "trap date",      str(date.date()))
    record_number("ERCOT Trap", "savings_fg_pct", pct, ".1f")
    return date


def plot_ercot_trap(df_5min: pd.DataFrame,
                    thresholds: pd.DataFrame,
                    trap_date: pd.Timestamp) -> None:

    thresh       = thresholds[thresholds["region"] == "ERCOT_NORTHCENTRAL"].iloc[0]
    green_thresh = float(thresh["green_threshold"])
    red_thresh   = float(thresh["red_threshold"])

    # 3-day window centred on trap date
    win_start = trap_date - pd.Timedelta(days=1)
    win_end   = trap_date + pd.Timedelta(days=2)

    ts = (
        df_5min[
            (df_5min["region"] == "ERCOT_NORTHCENTRAL") &
            (df_5min["point_time_local"] >= win_start) &
            (df_5min["point_time_local"] <  win_end)
        ]
        .sort_values("point_time_local")
        .set_index("point_time_local")["value"]
    )

    if len(ts) == 0:
        print("  ⚠️  No 5-min data found for ERCOT trap window — skipping Fig 1")
        return

    # Locate job window: first green interval in the operating window on trap_date
    op_day = ts[
        (ts.index.normalize() == trap_date.normalize()) &
        (ts.index.hour >= DAY_SHIFT_START) &
        (ts.index.hour <  DAY_SHIFT_END)
    ]
    green_starts = op_day[op_day.values <= green_thresh]
    job_start    = green_starts.index[0] if len(green_starts) else op_day.index[0]
    job_end      = job_start + pd.Timedelta(hours=2)
    job_ts       = ts[(ts.index >= job_start) & (ts.index <= job_end)]
    job_avg      = float(job_ts.mean())

    # Baseline: mean of all 2-hr rolling window means in the operating window
    ji      = 24   # 2 h × 12 intervals/h
    op_vals = op_day.values
    if len(op_vals) >= ji:
        cs       = np.concatenate([[0], np.cumsum(op_vals)])
        wm       = (cs[ji:] - cs[:len(op_vals) - ji + 1]) / ji
        baseline = float(np.mean(wm))
    else:
        baseline = float(op_day.mean())

    savings = (baseline - job_avg) / baseline * 100
    record_number("ERCOT Trap", "job avg MOER",  job_avg,  ".0f")
    record_number("ERCOT Trap", "baseline MOER", baseline, ".0f")
    record_number("ERCOT Trap", "savings %",     savings,  ".1f")

    ylo = float(ts.min()) * 0.97
    yhi = float(ts.max()) * 1.03

    with thesis_style():
        fig, ax = plt.subplots(figsize=(11, 4.5))

        # Traffic-light background bands
        ax.fill_between(ts.index, ylo, green_thresh,
                        color=GC, alpha=0.10, zorder=0, lw=0)
        ax.fill_between(ts.index, green_thresh, red_thresh,
                        color=YC, alpha=0.12, zorder=0, lw=0)
        ax.fill_between(ts.index, red_thresh, yhi,
                        color=RC, alpha=0.10, zorder=0, lw=0)
        ax.axhline(green_thresh, color=GC, lw=0.8, ls="--", alpha=0.55, zorder=1)
        ax.axhline(red_thresh,   color=RC, lw=0.8, ls="--", alpha=0.55, zorder=1)

        # Full MOER series
        ax.plot(ts.index, ts.values,
                color="#555555", lw=1.0, alpha=0.85, zorder=3)

        # Job window
        ax.axvspan(job_start, job_end,
                   alpha=0.22, color="#1f77b4", zorder=2, lw=0)
        ax.plot(job_ts.index, job_ts.values,
                color="#1f77b4", lw=2.4, zorder=5, solid_capstyle="round")

        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%b %d"))
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlim(ts.index[0], ts.index[-1])
        ax.set_ylim(ylo, yhi)
        ax.set_ylabel(f"MOER ({SIGNAL_UNIT})")
        ax.set_xlabel(f"Time of day — {trap_date.year}")
        ax.grid(axis="y", alpha=0.3, lw=0.5)

        ax.legend(
            handles=[mpatches.Patch(color="#1f77b4", alpha=0.6,
                                    label="2-hr job window")],
            fontsize=10, loc="upper right", framealpha=0.9,
        )

        save_fig(fig, "fig_supp_ercot_trap")


# =============================================================================
# FIG 2 — SPP KANSAS BIMODAL
# =============================================================================

def plot_spp_bimodal(df_5min: pd.DataFrame,
                     thresholds: pd.DataFrame) -> None:

    thresh = thresholds[thresholds["region"] == "SPP_KANSAS"].iloc[0]
    p25    = float(thresh["green_threshold"])
    p75    = float(thresh["red_threshold"])

    vals = df_5min[
        (df_5min["region"] == "SPP_KANSAS") &
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] <  DAY_SHIFT_END)
    ]["value"].dropna().values

    if len(vals) == 0:
        print("  ⚠️  No SPP_KANSAS data — skipping Fig 2")
        return

    cv = float(np.std(vals) / np.mean(vals))
    record_number("SPP Bimodal", "n records",   len(vals))
    record_number("SPP Bimodal", "P25 (green)", p25, ".0f")
    record_number("SPP Bimodal", "P75 (red)",   p75, ".0f")
    record_number("SPP Bimodal", "CV",           cv,  ".2f")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 4.5))

        ax.hist(vals, bins=130, density=True,
                color="#33BBEE", alpha=0.55,
                edgecolor="white", linewidth=0.2, zorder=2)

        kde   = gaussian_kde(vals, bw_method=0.04)
        x_kde = np.linspace(float(vals.min()), float(vals.max()), 1200)
        y_kde = kde(x_kde)
        ax.plot(x_kde, y_kde, color="#0b6e87", lw=2.0, zorder=3)

        ymax = ax.get_ylim()[1]
        span = p75 - p25

        ax.axvline(p25, color=GC, lw=1.8, ls="--", zorder=4)
        ax.axvline(p75, color=RC, lw=1.8, ls="--", zorder=4)

        ax.text(p25 + span * 0.02, ymax * 0.93,
                f"P25 = {p25:.0f}", fontsize=9, color=GC, va="top")
        ax.text(p75 + span * 0.02, ymax * 0.93,
                f"P75 = {p75:.0f}", fontsize=9, color=RC, va="top")

        ax.set_xlabel(f"MOER ({SIGNAL_UNIT})")
        ax.set_ylabel("Density")
        ax.grid(axis="y", alpha=0.3, lw=0.5)

        save_fig(fig, "fig_supp_spp_bimodal")


# =============================================================================
# FIG 3 — CAISO SEASONAL PROFILES
# =============================================================================

def plot_caiso_seasonal(df_5min: pd.DataFrame,
                        thresholds: pd.DataFrame) -> None:

    thresh      = thresholds[thresholds["region"] == "CAISO_NORTH"].iloc[0]
    caiso_green = float(thresh["green_threshold"])
    caiso_red   = float(thresh["red_threshold"])

    caiso = df_5min[
        (df_5min["region"] == "CAISO_NORTH") &
        (df_5min["hour"] >= DAY_SHIFT_START) &
        (df_5min["hour"] <  DAY_SHIFT_END)
    ]

    if len(caiso) == 0:
        print("  ⚠️  No CAISO_NORTH data — skipping Fig 3")
        return

    hours_in_window = list(range(DAY_SHIFT_START, DAY_SHIFT_END))
    hours_arr       = np.array(hours_in_window, dtype=float)

    # Mean MOER by season × hour across all years
    profiles = (
        caiso.groupby(["season", "hour"])["value"]
        .mean()
        .unstack(level="hour")
        .reindex(columns=hours_in_window)
    )

    record_number("CAISO Seasonal", "green threshold (op window)", caiso_green, ".0f")
    record_number("CAISO Seasonal", "red threshold (op window)",   caiso_red,   ".0f")
    for season in SEASON_ORDER:
        if season in profiles.index:
            record_number("CAISO Seasonal",
                          f"{season} op-window mean",
                          profiles.loc[season].mean(), ".0f")

    with thesis_style():
        fig, ax = plt.subplots(figsize=(11, 4.5))

        # Background bands (no labels)
        ax.axhspan(0,           caiso_green, color=GC, alpha=0.08, zorder=0, lw=0)
        ax.axhspan(caiso_green, caiso_red,   color=YC, alpha=0.10, zorder=0, lw=0)
        ax.axhspan(caiso_red,   9999,        color=RC, alpha=0.08, zorder=0, lw=0)
        ax.axhline(caiso_green, color=GC, lw=0.7, ls="--", alpha=0.45, zorder=1)
        ax.axhline(caiso_red,   color=RC, lw=0.7, ls="--", alpha=0.45, zorder=1)

        for season in SEASON_ORDER:
            if season not in profiles.index:
                print(f"  ⚠️  No data for season '{season}' in CAISO — skipping")
                continue
            mu    = profiles.loc[season].values.astype(float)
            color = SEASON_COLORS[season]
            ax.plot(hours_arr, mu, "-o",
                    color=color, lw=2.1, markersize=4.5, zorder=4,
                    label=season.capitalize())

        ax.set_xticks(hours_in_window)
        ax.set_xticklabels([f"{h:02d}:00" for h in hours_in_window], fontsize=8.5)
        ax.set_xlim(hours_in_window[0] - 0.5, hours_in_window[-1] + 0.5)
        ax.set_xlabel("Time of day (local)")
        ax.set_ylabel(f"MOER ({SIGNAL_UNIT})")
        ax.legend(loc="upper left", fontsize=12, framealpha=0.9,
                  markerscale=1.5, handlelength=2.2, labelspacing=0.5)
        ax.grid(axis="y", alpha=0.3, lw=0.5)

        save_fig(fig, "fig_supp_caiso_seasonal")


# =============================================================================
# MAIN
# =============================================================================

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--recompute", action="store_true",
                   help="Bypass simulation cache")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()

    print("Loading 5-min MOER data...")
    df_5min = load_5min()

    print("\nComputing thresholds...")
    thresholds = compute_thresholds(df_5min)

    print("\nRunning scheduling simulation (for ERCOT trap detection)...")
    sim_df = run_scheduling_sim(
        df_5min,
        use_cache=not args.recompute,
        cache_tag="supp_figs_v1",
    )

    print("\n── Fig 1: ERCOT first-green trap ──")
    trap_date = find_ercot_trap_date(sim_df)
    plot_ercot_trap(df_5min, thresholds, trap_date)

    print("\n── Fig 2: SPP Kansas bimodal ──")
    plot_spp_bimodal(df_5min, thresholds)

    print("\n── Fig 3: CAISO seasonal profiles ──")
    plot_caiso_seasonal(df_5min, thresholds)

    print(f"\nAll figures saved to {_cm.FIGURES_DIR}")