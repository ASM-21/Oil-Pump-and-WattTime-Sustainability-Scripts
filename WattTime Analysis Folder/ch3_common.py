"""
ch3_common.py — Shared utilities for Chapter 3 figure and table generation.
All chapter scripts import from here. Edit CONFIG to change behavior globally.

Expected file location: <project_root>/ch3/ch3_common.py
  - PROJECT_ROOT here refers to the ch3/ directory (for output paths)
  - config.py is one level up: Path(__file__).parent.parent
"""

import sys, json, hashlib, warnings
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).parent  # = ch3/ directory

# config.py lives one level up (the project root: watttime_analysis_V2/)
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import REGIONS as ALL_REGIONS, SEASONS, RUNS_DIR

# =============================================================================
# ▼▼▼ CONFIG — EDIT THIS SECTION ▼▼▼
# =============================================================================
RUN_DIR_NAME = "2026-02-26_GridMixStudy_Test_forcast and historical"  # ← CHANGE THIS

CH3_REGIONS = {
    "BPA":                  {"short": "BPA",      "label": "BPA (Hydro)",           "archetype": "Hydro-baseload"},
    "CAISO_NORTH":          {"short": "CAISO_N",  "label": "CAISO North (Solar)",   "archetype": "Solar-dominated"},
    "ERCOT_NORTHCENTRAL":   {"short": "ERCOT_NC", "label": "ERCOT N-Central (Wind-Gas)", "archetype": "Wind-gas mix"},
    "ISONE_CT":             {"short": "ISONE_CT", "label": "ISO-NE CT (Gas-Nuclear)","archetype": "Gas-nuclear"},
    "MISO_INDIANAPOLIS":    {"short": "MISO_INDY","label": "MISO Indianapolis (Coal)","archetype": "Coal-transitional"},
    "SPP_KANSAS":           {"short": "SPP_KS",   "label": "SPP Kansas (Wind)",     "archetype": "Wind-dominated"},
}

SIGNAL = "co2_moer"
SIGNAL_UNIT = "lbs CO₂/MWh"

DAY_SHIFT_START = 6
DAY_SHIFT_END   = 18
REFERENCE_JOB_HOURS = 2.0
INTERVALS_PER_HOUR = 12
GREEN_PERCENTILE = 25
RED_PERCENTILE   = 75

# "mean_green" = avg of all green-start windows; "first_green" = first green interval
# "persistent_green" = first green window sustained for PERSIST_INTERVALS
# "best_green" = green-start window with lowest avg MOER (requires full-day lookahead)
TL_STRATEGY = "first_green"
PERSIST_INTERVALS = 6   # 30 min at 5-min resolution; filters brief green blips
ALL_TL_STRATEGIES = ["first_green", "persistent_green", "best_green", "mean_green"]

CHARACTERIZATION_YEARS = [2021, 2022, 2023, 2024]
HOLDOUT_TRAIN_YEARS    = [2022, 2023]
HOLDOUT_TEST_YEARS     = [2024]
REP_WEEK_START = "2023-04-03"
DURATION_SWEEP_HOURS = [0.5, 1.0, 2.0, 4.0, 8.0]
FLEXIBILITY_DAYS = [1, 2, 3, 5, 7]
N_BOOTSTRAP = 1000
CI_LEVEL = 0.95

OUTPUT_DIR   = PROJECT_ROOT / "ch3_outputs"
FIGURES_DIR  = OUTPUT_DIR / "figures"
TABLES_DIR   = OUTPUT_DIR / "tables"
CACHE_DIR    = OUTPUT_DIR / "cache"
NUMBERS_FILE = OUTPUT_DIR / "ch3_numbers.md"
# ▲▲▲ END CONFIG ▲▲▲

# =============================================================================
# PALETTE
# =============================================================================
REGION_COLORS = {
    "BPA": "#0077BB", "CAISO_NORTH": "#EE7733", "ERCOT_NORTHCENTRAL": "#009988",
    "ISONE_CT": "#AA3377", "MISO_INDIANAPOLIS": "#555555", "SPP_KANSAS": "#33BBEE",
}
REGION_MARKERS = {
    "BPA": "o", "CAISO_NORTH": "s", "ERCOT_NORTHCENTRAL": "^",
    "ISONE_CT": "D", "MISO_INDIANAPOLIS": "v", "SPP_KANSAS": "P",
}
SEASON_ORDER = ["winter", "spring", "summer", "fall"]
SEASON_COLORS = {"winter": "#0077BB", "spring": "#009988", "summer": "#EE7733", "fall": "#CC3311"}
TRAFFIC_LIGHT_COLORS = {"green": "#2ca02c", "yellow": "#f0c929", "red": "#d62728"}

# =============================================================================
# THESIS STYLE
# =============================================================================
THESIS_RCPARAMS = {
    "font.family": "serif", "font.serif": ["Times New Roman", "DejaVu Serif"],
    "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 10,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 1.8, "figure.figsize": (8, 5),
}

@contextmanager
def thesis_style():
    with mpl.rc_context(THESIS_RCPARAMS):
        yield

# =============================================================================
# NUMBERS COLLECTOR
# =============================================================================
_numbers_registry: List[str] = []

def record_number(section: str, label: str, value, fmt: str = ".1f"):
    if isinstance(value, (int, np.integer)):
        formatted = str(value)
    elif isinstance(value, (float, np.floating)):
        formatted = f"{value:{fmt}}"
    else:
        formatted = str(value)
    entry = f"[{section}] {label}: {formatted}"
    _numbers_registry.append(entry)
    print(f"  📊 {entry}")

def export_numbers():
    NUMBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Chapter 3 — Computed Numbers", f"# {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}", ""]
    current_section = None
    for entry in _numbers_registry:
        sec = entry.split("]")[0].lstrip("[")
        if sec != current_section:
            lines.append(f"\n## {sec}")
            current_section = sec
        lines.append(f"- {entry}")
    NUMBERS_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ Numbers exported to {NUMBERS_FILE}")

# =============================================================================
# FILE I/O
# =============================================================================
def ensure_dirs():
    for d in [FIGURES_DIR, TABLES_DIR, CACHE_DIR]:
        d.mkdir(parents=True, exist_ok=True)

def save_fig(fig, name: str, figures_dir: Path = None):
    d = figures_dir or FIGURES_DIR; d.mkdir(parents=True, exist_ok=True)
    fig.savefig(d / f"{name}.png", dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(d / f"{name}.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  💾 {name}.png + .pdf")

def save_panel(fig, base_name: str, panel_label: str, figures_dir: Path = None):
    """Save individual panel file: fig_3_1_BPA.png/.pdf"""
    save_fig(fig, f"{base_name}_{panel_label}", figures_dir)

def save_table(df: pd.DataFrame, name: str, caption: str = ""):
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES_DIR / f"{name}.csv", index=False)
    with open(TABLES_DIR / f"{name}.md", "w", encoding="utf-8") as f:
        if caption: f.write(f"**{caption}**\n\n")
        f.write(df.to_markdown(index=False) + "\n")
    print(f"  💾 {name}.csv + .md")

# =============================================================================
# DATA LOADING
# =============================================================================
def get_run_dir() -> Path:
    run_dir = RUNS_DIR / RUN_DIR_NAME
    if not run_dir.exists():
        candidates = sorted(RUNS_DIR.glob(f"*{RUN_DIR_NAME}*"))
        if candidates:
            run_dir = candidates[-1]
        else:
            raise FileNotFoundError(f"Run dir not found: {run_dir}")
    return run_dir

def load_5min(run_dir: Path = None) -> pd.DataFrame:
    run_dir = run_dir or get_run_dir()
    df = pd.read_parquet(run_dir / "processed" / "data_5min.parquet")
    df = df[df["region"].isin(CH3_REGIONS.keys())].copy()
    for col in ["point_time_local", "date"]:
        if col in df.columns: df[col] = pd.to_datetime(df[col])
    if "season" not in df.columns: df["season"] = df["month"].map(_month_to_season)
    print(f"  Loaded 5-min: {len(df):,} records, {df['region'].nunique()} regions")
    return df

def load_hourly(run_dir: Path = None) -> pd.DataFrame:
    run_dir = run_dir or get_run_dir()
    df = pd.read_parquet(run_dir / "processed" / "data_hourly.parquet")
    df = df[df["region"].isin(CH3_REGIONS.keys())].copy()
    if "point_time" not in df.columns and "year" in df.columns:
        df["point_time"] = pd.to_datetime(df[["year","month","day","hour"]].assign(minute=0,second=0))
    for col in ["date"]:
        if col in df.columns: df[col] = pd.to_datetime(df[col])
    if "season" not in df.columns: df["season"] = df["month"].map(_month_to_season)
    print(f"  Loaded hourly: {len(df):,} records")
    return df

def _month_to_season(month):
    for s, ms in SEASONS.items():
        if month in ms: return s
    return "unknown"

# =============================================================================
# CACHING
# =============================================================================
def _cache_key(name, params):
    h = hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:8]
    return f"{name}_{h}"

def load_cache(name, params):
    path = CACHE_DIR / f"{_cache_key(name, params)}.parquet"
    if path.exists():
        print(f"  📦 Cache hit: {path.stem}")
        return pd.read_parquet(path)
    return None

def save_cache(df, name, params):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_DIR / f"{_cache_key(name, params)}.parquet", index=False)

# =============================================================================
# DUAL THRESHOLD COMPUTATION
# Returns both operating-window and all-hours thresholds.
# Operating-window thresholds are used for the simulation.
# =============================================================================
def compute_thresholds(df_5min: pd.DataFrame) -> pd.DataFrame:
    print("  Computing thresholds (both scopes)...")
    win = df_5min[(df_5min["hour"] >= DAY_SHIFT_START) & (df_5min["hour"] < DAY_SHIFT_END)]
    rows = []
    for region in CH3_REGIONS:
        rd_all = df_5min[df_5min["region"] == region]["value"]
        rd_win = win[win["region"] == region]["value"]
        if len(rd_all) == 0: continue
        g_all, r_all = rd_all.quantile(GREEN_PERCENTILE/100), rd_all.quantile(RED_PERCENTILE/100)
        g_win, r_win = rd_win.quantile(GREEN_PERCENTILE/100), rd_win.quantile(RED_PERCENTILE/100)
        rows.append({
            "region": region, "archetype": CH3_REGIONS[region]["archetype"],
            "green_threshold": g_win, "red_threshold": r_win,
            "green_threshold_allhours": g_all, "red_threshold_allhours": r_all,
            "mean_all": rd_all.mean(), "mean_window": rd_win.mean(),
        })
        s = CH3_REGIONS[region]["short"]
        print(f"    {s:10s} Win: G≤{g_win:,.0f} R≥{r_win:,.0f}  All: G≤{g_all:,.0f} R≥{r_all:,.0f}")
    return pd.DataFrame(rows)

# =============================================================================
# SIMULATION ENGINE — computes both TL strategies
#
# simulate_day: pure per-day simulation, no I/O
#   day_values    : 1-D array of 5-min MOER values in time order (shift window only)
#   job_intervals : number of 5-min intervals for the job (e.g. 2h → 24)
#   green/red_threshold : operating-window percentile thresholds
# =============================================================================
def simulate_day(day_values, job_intervals, green_threshold, red_threshold):
    n = len(day_values)
    if n < job_intervals: return None
    n_win = n - job_intervals + 1
    cs = np.concatenate([[0], np.cumsum(day_values)])
    wm = (cs[job_intervals:] - cs[:n_win]) / job_intervals  # rolling window means
    if len(wm) == 0: return None

    baseline = float(np.mean(wm))   # random start → mean of all window means
    optimal  = float(np.min(wm))    # perfect oracle

    # sm[k] = MOER at start of window k — this is the "traffic light" signal
    sm = day_values[:n_win]
    gm = sm <= green_threshold
    ym = (sm > green_threshold) & (sm < red_threshold)

    # --- STRATEGY 1: mean_green ---
    # Average emissions across all green-start windows
    if np.any(gm):   tl_mg = float(np.mean(wm[gm]))
    elif np.any(ym): tl_mg = float(np.mean(wm[ym]))
    else:            tl_mg = baseline

    # --- STRATEGY 2: first_green ---
    # Emissions for the first green-start window encountered
    if np.any(gm):   tl_fg = float(wm[np.where(gm)[0][0]])
    elif np.any(ym): tl_fg = float(wm[np.where(ym)[0][0]])
    else:            tl_fg = baseline

    # --- STRATEGY 3: best_green ---
    # Green-start window with the lowest average MOER (full-day lookahead)
    if np.any(gm):   tl_bg = float(np.min(wm[gm]))
    elif np.any(ym): tl_bg = float(np.min(wm[ym]))
    else:            tl_bg = baseline

    # --- STRATEGY 4: persistent_green ---
    # First green window where green persists for PERSIST_INTERVALS consecutive readings
    min_persist = PERSIST_INTERVALS
    tl_pg = None
    if np.any(gm) and min_persist > 1:
        # Check each position: are the next min_persist start-of-window readings all green?
        for i in range(n_win):
            end = i + min_persist
            if end > n_win:
                break
            if np.all(sm[i:end] <= green_threshold):
                tl_pg = float(wm[i])
                break
    if tl_pg is None:
        # Fall back through: any single green, then yellow, then baseline
        if np.any(gm):   tl_pg = float(wm[np.where(gm)[0][0]])
        elif np.any(ym): tl_pg = float(wm[np.where(ym)[0][0]])
        else:            tl_pg = baseline

    return {"baseline_moer": baseline, "optimal_moer": optimal,
            "tl_mean_green_moer": tl_mg, "tl_first_green_moer": tl_fg,
            "tl_best_green_moer": tl_bg, "tl_persistent_green_moer": tl_pg,
            "n_windows": n_win, "n_green_starts": int(gm.sum()), "n_yellow_starts": int(ym.sum())}


def run_scheduling_sim(df_5min, job_duration_hours=REFERENCE_JOB_HOURS,
                       shift_start=DAY_SHIFT_START, shift_end=DAY_SHIFT_END,
                       thresholds=None, years=None, use_cache=True, cache_tag="sim"):
    params = {"job": job_duration_hours, "shift": f"{shift_start}-{shift_end}",
              "years": years, "tag": cache_tag, "strategy": TL_STRATEGY}
    if use_cache:
        cached = load_cache(cache_tag, params)
        if cached is not None: return cached

    ji = int(job_duration_hours * INTERVALS_PER_HOUR)
    if thresholds is None: thresholds = compute_thresholds(df_5min)
    td = {r["region"]: (r["green_threshold"], r["red_threshold"]) for _, r in thresholds.iterrows()}
    results = []
    for region in CH3_REGIONS:
        if region not in td: continue
        gt, rt = td[region]
        rd = df_5min[(df_5min["region"]==region) & (df_5min["hour"]>=shift_start) & (df_5min["hour"]<shift_end)]
        if years: rd = rd[rd["year"].isin(years)]
        rd = rd.sort_values("point_time_local")
        for date, ddf in rd.groupby("date"):
            r = simulate_day(ddf["value"].values, ji, gt, rt)  # day_hours removed
            if r is None: continue
            b, o = r["baseline_moer"], r["optimal_moer"]
            mg = r["tl_mean_green_moer"]
            fg = r["tl_first_green_moer"]
            bg = r["tl_best_green_moer"]
            pg = r["tl_persistent_green_moer"]
            # Canonical strategy selects which one is "the" TL result
            strat_map = {"first_green": fg, "mean_green": mg,
                         "best_green": bg, "persistent_green": pg}
            tl = strat_map.get(TL_STRATEGY, fg)
            so = (b-o)/b*100 if b>0 else 0
            st = (b-tl)/b*100 if b>0 else 0
            results.append({
                "region": region, "date": date, "year": ddf["year"].iloc[0],
                "month": ddf["month"].iloc[0], "season": ddf["season"].iloc[0],
                "baseline_moer": b, "optimal_moer": o,
                "tl_mean_green_moer": mg, "tl_first_green_moer": fg,
                "tl_best_green_moer": bg, "tl_persistent_green_moer": pg,
                "traffic_light_moer": tl,
                "savings_optimal_pct": so, "savings_tl_pct": st,
                "savings_mg_pct": (b-mg)/b*100 if b>0 else 0,
                "savings_fg_pct": (b-fg)/b*100 if b>0 else 0,
                "savings_bg_pct": (b-bg)/b*100 if b>0 else 0,
                "savings_pg_pct": (b-pg)/b*100 if b>0 else 0,
                "capture_rate": st/so if so>0 else 1.0,
                "n_green_starts": r["n_green_starts"],
            })
    sim_df = pd.DataFrame(results)
    if use_cache and len(sim_df) > 0: save_cache(sim_df, cache_tag, params)
    print(f"  ✅ Sim done: {len(sim_df):,} region-days")
    return sim_df

# =============================================================================
# STABILITY SCORING (5-min data, Pearson on diurnal profiles + hour drift)
# =============================================================================
def compute_stability_scores(df_5min):
    print("\n  Stability scores (5-min, Pearson)...")
    rows = []
    for region in CH3_REGIONS:
        rd = df_5min[df_5min["region"] == region]
        for season in SEASON_ORDER:
            sd = rd[rd["season"] == season]
            if len(sd) == 0: continue
            mean_prof = sd.groupby("hour")["value"].mean()
            years = sorted(sd["year"].unique())
            corrs, bhours = [], []
            for yr in years:
                yp = sd[sd["year"]==yr].groupby("hour")["value"].mean()
                c = mean_prof.index.intersection(yp.index)
                if len(c) < 12: continue
                corrs.append(np.corrcoef(mean_prof[c], yp[c])[0,1])
                wp = yp[(yp.index>=DAY_SHIFT_START)&(yp.index<DAY_SHIFT_END)]
                if len(wp)>0: bhours.append(int(wp.idxmin()))
            if corrs:
                rows.append({"region": region, "season": season,
                             "stability_score": min(corrs), "mean_corr": np.mean(corrs),
                             "is_stable": min(corrs)>=0.7, "n_years": len(corrs),
                             "best_hours_by_year": bhours,
                             "hour_spread": max(bhours)-min(bhours) if bhours else 0})
    stab = pd.DataFrame(rows)
    if len(stab)>0:
        record_number("Section 3.4.4", "Mean stability score", stab["stability_score"].mean(), ".2f")
        record_number("Section 3.4.4", "% combos ≥ 0.7", (stab["stability_score"]>=0.7).mean()*100, ".0f")
    return stab

# =============================================================================
# GREEN WINDOW DURATION (5-min resolution)
# =============================================================================
def analyze_green_windows(df_5min, thresholds):
    print("\n  Green window durations (5-min)...")
    td = {r["region"]: r["green_threshold"] for _, r in thresholds.iterrows()}
    rows = []
    for region in CH3_REGIONS:
        if region not in td: continue
        gt = td[region]
        rd = df_5min[df_5min["region"]==region].sort_values("point_time_local").copy()
        rd["is_green"] = rd["value"] <= gt
        durs = []
        for _, ddf in rd.groupby("date"):
            rl = 0
            for g in ddf["is_green"].values:
                if g: rl += 1
                else:
                    if rl > 0: durs.append(rl)
                    rl = 0
            if rl > 0: durs.append(rl)
        if durs:
            dh = np.array(durs) / INTERVALS_PER_HOUR
            rows.append({"region": region, "mean_h": dh.mean(), "median_h": np.median(dh),
                         "pct_gt_2h": (dh>=2).mean()*100, "n_windows": len(dh),
                         "green_h_per_day": rd.groupby("date")["is_green"].sum().mean()/INTERVALS_PER_HOUR})
            record_number("Section 3.4.2", f"{CH3_REGIONS[region]['short']} mean green win (h)", dh.mean(), ".1f")
            record_number("Section 3.4.2", f"{CH3_REGIONS[region]['short']} % ≥2h", (dh>=2).mean()*100, ".0f")
    return pd.DataFrame(rows)

# =============================================================================
# BOOTSTRAP CI
# =============================================================================
def bootstrap_ci(data, statistic=np.mean, n_boot=N_BOOTSTRAP, ci=CI_LEVEL):
    rng = np.random.default_rng(42)
    bs = [statistic(rng.choice(data, len(data), replace=True)) for _ in range(n_boot)]
    a = (1-ci)/2
    return np.percentile(bs, 100*a), np.percentile(bs, 100*(1-a))

# =============================================================================
# ANNUAL TONNAGE
# savings_moer [lbs/MWh] × job_kwh/1000 [MWh] → lbs/job ÷ 2204.62 → metric tonnes/job
# × units × days → metric tonnes/yr
# =============================================================================
def compute_annual_tonnes(savings_moer, job_kwh=2.0, units=100, days=250):
    return savings_moer * job_kwh / 1000 / 2204.62 * units * days

# =============================================================================
# HELPERS
# =============================================================================
def rlabel(r): return CH3_REGIONS.get(r,{}).get("label",r)
def rshort(r): return CH3_REGIONS.get(r,{}).get("short",r)
def rcolor(r): return REGION_COLORS.get(r,"#333")
def rmarker(r): return REGION_MARKERS.get(r,"o")
def get_season(m): return _month_to_season(m)

def init():
    ensure_dirs()
    warnings.filterwarnings("ignore", category=FutureWarning)
    print("="*60)
    print("Chapter 3 — Carbon-Aware Manufacturing Scheduling")
    print("="*60)
    print(f"  Run: {RUN_DIR_NAME}  |  TL strategy: {TL_STRATEGY}")
    print(f"  Window: {DAY_SHIFT_START:02d}:00–{DAY_SHIFT_END:02d}:00  |  Job: {REFERENCE_JOB_HOURS}h")
    print(f"  Output: {OUTPUT_DIR}\n")