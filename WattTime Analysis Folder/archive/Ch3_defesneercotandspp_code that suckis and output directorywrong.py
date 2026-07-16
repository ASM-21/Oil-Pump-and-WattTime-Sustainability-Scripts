"""
fig_ercot_spp.py — Defense figures: ERCOT traffic-light backfire + SPP bimodal

Figure 1: ERCOT — first-green trigger starts in a wind burst that doesn't last
Figure 2: SPP  — bimodal MOER distribution (wind-on vs wind-off)

Run from project root (watttime_analysis_V2/):
    python fig_ercot_spp.py

Outputs saved to ch3_outputs/figures/
"""

import sys
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from scipy.stats import gaussian_kde

# ---------------------------------------------------------------------------
# CONFIG — edit here if paths differ
# ---------------------------------------------------------------------------
PROJECT_ROOT    = Path(__file__).resolve().parent.parent  # scripts/ → project root
RUN_DIR_NAME    = "2026-02-26_GridMixStudy_Test_forcast and historical"
DATA_PATH       = PROJECT_ROOT / "runs" / RUN_DIR_NAME / "processed" / "data_5min.parquet"
OUTPUT_DIR      = PROJECT_ROOT / "ch3_outputs" / "figures"

DAY_SHIFT_START = 6
DAY_SHIFT_END   = 18
JOB_HOURS       = 2.0
INTERVALS_PER_HOUR = 12   # 5-min resolution
JOB_INTERVALS   = int(JOB_HOURS * INTERVALS_PER_HOUR)  # 24 intervals

# Thresholds — override here or set to None to compute from data
ERCOT_P25_OVERRIDE = 1102.0
ERCOT_P75_OVERRIDE = 1165.0
SPP_P25_OVERRIDE   = 123.0
SPP_P75_OVERRIDE   = 1401.0

STUDY_YEARS = [2021, 2022, 2023, 2024]

# Colors matching ch3_common palette
C_GREEN  = "#2ecc71"
C_YELLOW = "#f39c12"
C_RED    = "#e74c3c"
C_ERCOT  = "#009988"
C_SPP    = "#33BBEE"
C_MISO   = "#555555"

ALPHA_BAND = 0.18
ALPHA_RECT = 0.30

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_data():
    df = pd.read_parquet(DATA_PATH)
    # Filter to co2_moer signal and rename value col
    if "signal" in df.columns:
        df = df[df["signal"] == "co2_moer"].copy()
    df = df.rename(columns={"value": "co2_moer"})
    for col in ["point_time_local", "date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    if "hour" not in df.columns:
        df["hour"] = df["point_time_local"].dt.hour
    if "year" not in df.columns:
        df["year"] = df["point_time_local"].dt.year
    df_day = df[(df["hour"] >= DAY_SHIFT_START) & (df["hour"] < DAY_SHIFT_END)].copy()
    print(f"  Loaded {len(df):,} co2_moer records across {df['region'].nunique()} regions")
    return df, df_day


def get_thresholds(series, p25_override=None, p75_override=None):
    p25 = p25_override if p25_override is not None else np.percentile(series.dropna(), 25)
    p75 = p75_override if p75_override is not None else np.percentile(series.dropna(), 75)
    return p25, p75


def find_ercot_backfire_day(ercot_day: pd.DataFrame, p25: float, p75: float):
    """
    Find the best illustration day for Figure 1.
    Criteria:
      1. A 5-min interval crosses below P25 (first-green trigger fires)
      2. Within the subsequent JOB_INTERVALS window, MOER rises above P75
      3. Prefer days where the pre-trigger period is clearly elevated (makes the
         contrast obvious) and the dip is brief (~1–3 intervals).
    Returns the date string and the trigger interval index within that day.
    """
    best_day   = None
    best_idx   = None
    best_score = -np.inf

    for date, grp in ercot_day.groupby("date"):
        grp = grp.sort_values("point_time_local").reset_index(drop=True)
        vals = grp["co2_moer"].values
        n = len(vals)
        if n < JOB_INTERVALS + 4:
            continue

        for i in range(n - JOB_INTERVALS):
            if vals[i] >= p25:
                continue  # not a green trigger
            # Check window includes yellow/red territory
            window = vals[i : i + JOB_INTERVALS]
            pct_above_p25 = np.mean(window > p25)
            pct_above_p75 = np.mean(window > p75)
            if pct_above_p75 < 0.15:
                continue  # window stays mostly green — not a good illustration

            # Pre-trigger context: want elevated MOER leading up to the dip
            pre_window_start = max(0, i - 12)
            pre_vals = vals[pre_window_start:i]
            pre_mean = np.mean(pre_vals) if len(pre_vals) > 0 else 0

            # Prefer: brief green dip, high post-trigger MOER, elevated pre-dip
            dip_length = 1
            while i + dip_length < n and vals[i + dip_length] < p25:
                dip_length += 1
            if dip_length > 8:
                continue  # dip too long — not a "burst"

            score = (pct_above_p75 * 3.0          # reward red territory in window
                     + pct_above_p25 * 1.0         # reward yellow territory too
                     + (pre_mean - p25) / 200.0    # reward elevated pre-context
                     - dip_length * 0.2)            # penalize long dips (want brief bursts)

            if score > best_score:
                best_score = score
                best_day   = date
                best_idx   = i

    return best_day, best_idx


# ---------------------------------------------------------------------------
# Figure 1: ERCOT backfire
# ---------------------------------------------------------------------------
def plot_fig1_ercot_backfire(ercot_day: pd.DataFrame, p25: float, p75: float,
                              out_dir: Path):
    chosen_date, trigger_idx = find_ercot_backfire_day(ercot_day, p25, p75)

    if chosen_date is None:
        print("  ⚠ No ideal backfire day found — relaxing criteria and picking best candidate")
        # Fall back: first day with any green trigger whose window average > p25
        for date, grp in ercot_day.groupby("date"):
            grp = grp.sort_values("point_time_local").reset_index(drop=True)
            vals = grp["co2_moer"].values
            for i in range(len(vals) - JOB_INTERVALS):
                if vals[i] < p25 and np.mean(vals[i:i+JOB_INTERVALS]) > p25:
                    chosen_date, trigger_idx = date, i
                    break
            if chosen_date: break

    grp = (ercot_day[ercot_day["date"] == chosen_date]
           .sort_values("point_time_local").reset_index(drop=True))
    vals  = grp["co2_moer"].values
    times = grp["point_time_local"].values  # numpy datetime64

    # Convert to hour-of-day floats for x-axis
    t0 = pd.Timestamp(times[0])
    hours = np.array([(pd.Timestamp(t) - t0.normalize()).total_seconds() / 3600
                      for t in times])
    date_str = pd.Timestamp(chosen_date).strftime("%B %d, %Y")
    print(f"  Fig 1 — ERCOT backfire day: {date_str}  trigger_idx={trigger_idx}")

    # ---- find forecast-optimal window (lowest mean 2-hr window) ----
    best_opt_i = 0
    best_opt_val = np.inf
    for i in range(len(vals) - JOB_INTERVALS + 1):
        m = np.mean(vals[i:i+JOB_INTERVALS])
        if m < best_opt_val:
            best_opt_val = m
            best_opt_i = i

    # ---- plot ----
    fig, ax = plt.subplots(figsize=(8.5, 4.0))

    ymin = max(0, min(vals) - 80)
    ymax = max(vals) + 80

    # Horizontal traffic-light bands (full width)
    ax.axhspan(ymin,  p25,  color=C_GREEN,  alpha=ALPHA_BAND, zorder=0)
    ax.axhspan(p25,   p75,  color=C_YELLOW, alpha=ALPHA_BAND, zorder=0)
    ax.axhspan(p75,   ymax, color=C_RED,    alpha=ALPHA_BAND, zorder=0)

    # Threshold lines
    ax.axhline(p25, color=C_GREEN,  lw=0.9, ls="--", alpha=0.7, zorder=1)
    ax.axhline(p75, color=C_RED,    lw=0.9, ls="--", alpha=0.7, zorder=1)
    ax.text(DAY_SHIFT_START + 0.08, p25 + 8, f"P25 = {p25:,.0f}", fontsize=7.5,
            color=C_GREEN, va="bottom")
    ax.text(DAY_SHIFT_START + 0.08, p75 + 8, f"P75 = {p75:,.0f}", fontsize=7.5,
            color=C_RED, va="bottom")

    # MOER line
    ax.plot(hours, vals, color=C_ERCOT, lw=1.8, zorder=3, label="MOER (5-min)")

    # ---- First-green trigger window (blue rectangle) ----
    trig_h_start = hours[trigger_idx]
    trig_h_end   = trig_h_start + JOB_HOURS
    trig_rect = mpatches.FancyArrowPatch  # just using Rectangle below
    rect_trig = mpatches.Rectangle(
        (trig_h_start, ymin), JOB_HOURS, ymax - ymin,
        linewidth=1.8, edgecolor="#2C3E50", facecolor="#2C3E50",
        alpha=ALPHA_RECT, zorder=2, label="First-green window (2 hr)"
    )
    ax.add_patch(rect_trig)

    # Annotation: job starts
    ax.annotate(
        "Job starts\n(green trigger)",
        xy=(trig_h_start, p25 - 15),
        xytext=(trig_h_start - 0.15, p25 - 90),
        fontsize=7.5, ha="right", va="top", color="#2C3E50",
        arrowprops=dict(arrowstyle="-|>", color="#2C3E50", lw=1.0),
        zorder=5
    )

    # Annotation: job still running (centered in yellow/red portion)
    # find the midpoint of the window that is above p25
    window_hours = np.linspace(trig_h_start, trig_h_end, JOB_INTERVALS)
    window_vals  = vals[trigger_idx:trigger_idx + JOB_INTERVALS]
    above_p25_mask = window_vals > p25
    if above_p25_mask.any():
        mid_above = np.mean(window_hours[above_p25_mask])
        mid_y     = np.mean(window_vals[above_p25_mask])
        ax.annotate(
            "Job still running\n(conditions changed)",
            xy=(mid_above, mid_y + 5),
            xytext=(mid_above + 0.3, mid_y + 100),
            fontsize=7.5, ha="left", va="bottom", color="#7f0000",
            arrowprops=dict(arrowstyle="-|>", color="#7f0000", lw=1.0),
            zorder=5
        )

    # ---- Forecast-optimal window (dashed outline only — contrast) ----
    if best_opt_i != trigger_idx:
        opt_h_start = hours[best_opt_i]
        rect_opt = mpatches.Rectangle(
            (opt_h_start, ymin), JOB_HOURS, ymax - ymin,
            linewidth=1.8, edgecolor="#1a9641", facecolor="none",
            linestyle="--", zorder=2, label="Forecast-optimal window (2 hr)"
        )
        ax.add_patch(rect_opt)
        ax.text(opt_h_start + JOB_HOURS / 2, ymax - 35,
                "Forecast\noptimal", fontsize=7, ha="center",
                color="#1a9641", style="italic")

    ax.set_xlim(DAY_SHIFT_START, DAY_SHIFT_END)
    ax.set_ylim(ymin, ymax)
    ax.set_xlabel("Hour of day (local time)", fontsize=9)
    ax.set_ylabel("MOER (lbs CO₂/MWh)", fontsize=9)
    ax.set_xticks(range(DAY_SHIFT_START, DAY_SHIFT_END + 1, 2))
    ax.set_xticklabels([f"{h:02d}:00" for h in range(DAY_SHIFT_START, DAY_SHIFT_END + 1, 2)],
                       fontsize=8)
    ax.tick_params(axis="y", labelsize=8)

    ax.set_title(
        f"ERCOT N-Central: First-green trigger captures a wind burst that doesn't last\n"
        f"({date_str})",
        fontsize=9, pad=8
    )
    ax.legend(fontsize=7.5, loc="upper right", framealpha=0.85)

    # Band legend (custom patches)
    band_patches = [
        mpatches.Patch(color=C_GREEN,  alpha=0.55, label="Green  (< P25)"),
        mpatches.Patch(color=C_YELLOW, alpha=0.55, label="Yellow (P25–P75)"),
        mpatches.Patch(color=C_RED,    alpha=0.55, label="Red    (> P75)"),
    ]
    leg2 = ax.legend(handles=band_patches, fontsize=7.5, loc="lower right",
                     framealpha=0.85, title="Traffic-light zones", title_fontsize=7.5)
    ax.add_artist(leg2)
    # Restore first legend
    ax.legend(fontsize=7.5, loc="upper right", framealpha=0.85)

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "pdf"]:
        fig.savefig(out_dir / f"fig_ercot_backfire.{ext}", dpi=300, bbox_inches="tight",
                    facecolor="white")
    plt.close(fig)
    print(f"  💾 fig_ercot_backfire.png / .pdf  →  {out_dir}")


# ---------------------------------------------------------------------------
# Figure 2: SPP bimodal distribution
# ---------------------------------------------------------------------------
def plot_fig2_spp_bimodal(df_day: pd.DataFrame,
                           spp_p25: float, spp_p75: float,
                           out_dir: Path):
    """
    Left panel : SPP KDE + histogram
    Right panel: MISO (or ISONE) for unimodal contrast
    """
    spp_vals  = df_day.loc[df_day["region"] == "SPP_KANSAS",  "co2_moer"].dropna().values

    # pick contrast region — prefer MISO_INDIANAPOLIS, fallback ISONE_CT
    contrast_region = None
    for r in ["MISO_INDIANAPOLIS", "ISONE_CT"]:
        if r in df_day["region"].values:
            contrast_region = r
            break
    contrast_label = {"MISO_INDIANAPOLIS": "MISO Indianapolis", "ISONE_CT": "ISO-NE CT"}.get(contrast_region, "")
    contrast_color = {"MISO_INDIANAPOLIS": C_MISO, "ISONE_CT": "#AA3377"}.get(contrast_region, "#555555")

    has_contrast = contrast_region is not None and len(
        df_day.loc[df_day["region"] == contrast_region, "co2_moer"].dropna()
    ) > 100

    ncols = 2 if has_contrast else 1
    fig, axes = plt.subplots(1, ncols, figsize=(8.5 if has_contrast else 5.5, 4.2),
                             sharey=False)
    if ncols == 1:
        axes = [axes]

    def draw_kde_panel(ax, vals, color, label, p25, p75, show_ylabel=True):
        # Histogram (normalized density)
        ax.hist(vals, bins=80, density=True, color=color, alpha=0.30,
                edgecolor="none", zorder=1)

        # KDE
        kde  = gaussian_kde(vals, bw_method="scott")
        xmin = max(0, vals.min() - 50)
        xmax = vals.max() + 50
        xs   = np.linspace(xmin, xmax, 600)
        ys   = kde(xs)
        ax.plot(xs, ys, color=color, lw=2.2, zorder=3)

        # P25 / P75 lines
        ax.axvline(p25, color=C_GREEN,  lw=1.5, ls="--", zorder=4,
                   label=f"P25 = {p25:,.0f}")
        ax.axvline(p75, color=C_RED,    lw=1.5, ls="--", zorder=4,
                   label=f"P75 = {p75:,.0f}")

        ax.set_xlabel("MOER (lbs CO₂/MWh)", fontsize=9)
        if show_ylabel:
            ax.set_ylabel("Density", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.set_title(label, fontsize=9, pad=6)
        ax.legend(fontsize=7.5, framealpha=0.85)

        # Annotate the two SPP peaks if this is the SPP panel
        if "SPP" in label:
            # low peak
            low_mask = xs < 400
            if low_mask.any():
                low_peak_x = xs[low_mask][np.argmax(ys[low_mask])]
                ax.annotate("Wind-on\n(near zero)", xy=(low_peak_x, ys[xs < 400].max()),
                            xytext=(low_peak_x + 150, ys[xs < 400].max() * 1.3),
                            fontsize=7.5, ha="left", color="#1a6b3c",
                            arrowprops=dict(arrowstyle="-|>", color="#1a6b3c", lw=0.9))
            # high peak
            high_mask = xs > 1000
            if high_mask.any():
                high_peak_x = xs[high_mask][np.argmax(ys[high_mask])]
                ax.annotate("Wind-off\n(gas peakers)", xy=(high_peak_x, ys[high_mask].max()),
                            xytext=(high_peak_x - 300, ys[high_mask].max() * 1.35),
                            fontsize=7.5, ha="right", color="#7f0000",
                            arrowprops=dict(arrowstyle="-|>", color="#7f0000", lw=0.9))

    # SPP panel
    draw_kde_panel(axes[0], spp_vals, C_SPP,
                   f"SPP Kansas  (n = {len(spp_vals):,})",
                   spp_p25, spp_p75, show_ylabel=True)

    # Contrast panel
    if has_contrast:
        c_vals = df_day.loc[df_day["region"] == contrast_region, "co2_moer"].dropna().values
        # compute contrast thresholds from data
        c_p25 = np.percentile(c_vals, 25)
        c_p75 = np.percentile(c_vals, 75)
        draw_kde_panel(axes[1], c_vals, contrast_color,
                       f"{contrast_label}  (n = {len(c_vals):,})",
                       c_p25, c_p75, show_ylabel=False)

    fig.suptitle(
        "SPP MOER Distribution: Wind-on vs Wind-off\n"
        "(Day-shift hours only, 2021–2024)",
        fontsize=9.5, y=1.01
    )
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ["png", "pdf"]:
        fig.savefig(out_dir / f"fig_spp_bimodal.{ext}", dpi=300, bbox_inches="tight",
                    facecolor="white")
    plt.close(fig)
    print(f"  💾 fig_spp_bimodal.png / .pdf  →  {out_dir}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("Loading data...")
    df, df_day = load_data()

    # ERCOT
    ercot_day = df_day[df_day["region"] == "ERCOT_NORTHCENTRAL"].copy()
    ercot_all = df_day[df_day["region"] == "ERCOT_NORTHCENTRAL"]["co2_moer"].dropna()
    e_p25, e_p75 = get_thresholds(ercot_all, ERCOT_P25_OVERRIDE, ERCOT_P75_OVERRIDE)
    print(f"  ERCOT thresholds: P25={e_p25:.0f}, P75={e_p75:.0f}  "
          f"({'overridden' if ERCOT_P25_OVERRIDE else 'computed'})")

    # SPP
    spp_all = df_day[df_day["region"] == "SPP_KANSAS"]["co2_moer"].dropna()
    s_p25, s_p75 = get_thresholds(spp_all, SPP_P25_OVERRIDE, SPP_P75_OVERRIDE)
    print(f"  SPP   thresholds: P25={s_p25:.0f}, P75={s_p75:.0f}  "
          f"({'overridden' if SPP_P25_OVERRIDE else 'computed'})")

    print("\nGenerating Figure 1: ERCOT backfire...")
    plot_fig1_ercot_backfire(ercot_day, e_p25, e_p75, OUTPUT_DIR)

    print("\nGenerating Figure 2: SPP bimodal...")
    plot_fig2_spp_bimodal(df_day, s_p25, s_p75, OUTPUT_DIR)

    print("\n✅ Done.")


if __name__ == "__main__":
    # matplotlib backend safe for headless / local
    mpl.use("Agg")
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linewidth": 0.5,
    })
    main()