"""
ch3_extended_health_cobenefits.py — Does minimizing carbon also reduce health harm?

CAISO-only case study comparing MOER (carbon) and health_damage (criteria pollutants).
Tests whether carbon-aware scheduling provides health co-benefits or creates a tradeoff.

Note: WattTime's health_damage signal is a modeled monetized health impact ($/MWh)
from criteria pollutants (NOx, SOx, PM2.5). We compare two modeled signals, not raw
measurements. The methodology generalizes to any region where both signals are available.

Research question:
    "When you schedule to minimize carbon, do you also reduce health-damaging
    pollution — or create a tradeoff?"

Outputs:
    Figures:
        fig_ext_moer_vs_health_diurnal.png/pdf
        fig_ext_health_correlation.png/pdf
        fig_ext_health_scheduling.png/pdf
    Tables:
        table_ext_health_cobenefits.csv/md

Usage:
    python ch3_extended_health_cobenefits.py
    python ch3_extended_health_cobenefits.py --recompute
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import sys

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, simulate_day,
    CH3_REGIONS, REGION_COLORS,
    SIGNAL_UNIT, DAY_SHIFT_START, DAY_SHIFT_END,
    REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    GREEN_PERCENTILE, RED_PERCENTILE, TL_STRATEGY,
    rshort, rcolor,
    FIGURES_DIR, save_cache, load_cache,
)

# Access project-level config for region metadata and library path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import REGIONS as ALL_REGIONS, LIBRARY_DIR, SEASONS

HEALTH_REGION = "CAISO_NORTH"
HEALTH_SIGNAL = "health_damage"
HEALTH_UNIT = "$/MWh"


def load_health_data():
    """Load health_damage data directly from library parquet file."""
    print("\n  Loading health_damage data from library...")
    health_path = LIBRARY_DIR / HEALTH_SIGNAL / "historical" / f"{HEALTH_REGION}.parquet"
    if not health_path.exists():
        print(f"  ⚠️ File not found: {health_path}")
        print(f"  To collect: set SIGNAL='health_damage' in 01_data_collection_v2.py")
        return None
    try:
        df = pd.read_parquet(health_path)
        if len(df) == 0:
            return None
        if "value" not in df.columns:
            val_cols = [c for c in df.columns if c not in
                        ["point_time","region","frequency","market","ba","signal_type"]]
            if val_cols:
                df = df.rename(columns={val_cols[0]: "value"})
            else:
                print(f"  ⚠️ No value column. Columns: {df.columns.tolist()}")
                return None
        if "point_time" in df.columns:
            df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
            tz = ALL_REGIONS[HEALTH_REGION]["timezone"]
            df["point_time_local"] = df["point_time"].dt.tz_convert(tz).dt.tz_localize(None)
        elif "point_time_local" in df.columns:
            df["point_time_local"] = pd.to_datetime(df["point_time_local"])
        else:
            print("  ⚠️ No timestamp column found"); return None
        df["hour"] = df["point_time_local"].dt.hour
        df["date"] = df["point_time_local"].dt.normalize()
        df["month"] = df["point_time_local"].dt.month
        df["region"] = HEALTH_REGION
        for s, ms in SEASONS.items():
            df.loc[df["month"].isin(ms), "season"] = s
        print(f"  ✅ {len(df):,} records, {df['date'].min().date()} to {df['date'].max().date()}")
        return df
    except Exception as e:
        print(f"  ⚠️ Failed: {e}"); return None


def compute_diurnal_comparison(df_moer, df_health):
    print("\n── Diurnal profile comparison ──")
    moer_hourly = df_moer[df_moer["region"] == HEALTH_REGION].groupby("hour")["value"].mean()
    health_hourly = df_health.groupby("hour")["value"].mean()
    common = moer_hourly.index.intersection(health_hourly.index)
    corr = np.corrcoef(moer_hourly[common], health_hourly[common])[0,1] if len(common)>=12 else np.nan
    record_number("Health", "MOER-health diurnal profile correlation", corr, ".3f")
    return moer_hourly, health_hourly, corr


def plot_diurnal_comparison(moer_hourly, health_hourly, corr):
    print("\n── Fig: MOER vs health diurnal ──")
    with thesis_style():
        fig, ax1 = plt.subplots(figsize=(10, 5))
        ax2 = ax1.twinx()
        ax1.plot(moer_hourly.index, moer_hourly.values, color="#4575b4", linewidth=2.5, label=f"MOER ({SIGNAL_UNIT})")
        ax2.plot(health_hourly.index, health_hourly.values, color="#d73027", linewidth=2.5, linestyle="--", label=f"Health ({HEALTH_UNIT})")
        ax1.axvspan(DAY_SHIFT_START, DAY_SHIFT_END, alpha=0.05, color="green")
        ax1.set_xlabel("Hour of Day"); ax1.set_ylabel(f"MOER ({SIGNAL_UNIT})", color="#4575b4")
        ax2.set_ylabel(f"Health Damage ({HEALTH_UNIT})", color="#d73027"); ax1.set_xlim(0,23)
        l1,la1 = ax1.get_legend_handles_labels(); l2,la2 = ax2.get_legend_handles_labels()
        ax1.legend(l1+l2, la1+la2, fontsize=9, loc="upper left")
        if not np.isnan(corr):
            ax1.text(0.98, 0.95, f"r = {corr:.2f}", transform=ax1.transAxes, fontsize=11, ha="right", va="top",
                     bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))
        save_fig(fig, "fig_ext_moer_vs_health_diurnal")


def compute_hourly_correlation(df_moer, df_health):
    print("\n── Hourly correlation ──")
    moer_hr = df_moer[df_moer["region"]==HEALTH_REGION].groupby(["date","hour"])["value"].mean().reset_index().rename(columns={"value":"moer"})
    health_hr = df_health.groupby(["date","hour"])["value"].mean().reset_index().rename(columns={"value":"health"})
    merged = moer_hr.merge(health_hr, on=["date","hour"], how="inner")
    rows = []
    for hour in range(24):
        hd = merged[merged["hour"]==hour]
        if len(hd)<30: continue
        rows.append({"hour": hour, "correlation": hd["moer"].corr(hd["health"]), "n": len(hd)})
    corr_df = pd.DataFrame(rows)
    op = corr_df[(corr_df["hour"]>=DAY_SHIFT_START)&(corr_df["hour"]<DAY_SHIFT_END)]
    if len(op)>0:
        mn = op.loc[op["correlation"].idxmin()]
        record_number("Health", "Lowest corr hour", int(mn["hour"]), "d")
        record_number("Health", "Lowest corr value", mn["correlation"], ".2f")
        record_number("Health", "Mean op-window corr", op["correlation"].mean(), ".2f")
    return corr_df


def plot_hourly_correlation(corr_df):
    print("\n── Fig: Hourly correlation ──")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(10, 4))
        colors = ["#4575b4" if DAY_SHIFT_START<=h<DAY_SHIFT_END else "#cccccc" for h in corr_df["hour"]]
        ax.bar(corr_df["hour"], corr_df["correlation"], color=colors, edgecolor="white")
        ax.axhline(0.7, color="green", linestyle="--", linewidth=0.8, alpha=0.6, label="Strong (r=0.7)")
        ax.axhline(0, color="gray", linewidth=0.5)
        ax.set_xlabel("Hour of Day"); ax.set_ylabel("MOER–Health Correlation")
        ax.set_xlim(-0.5,23.5); ax.set_xticks(range(0,24,3)); ax.set_ylim(-0.2,1.05); ax.legend(fontsize=8)
        save_fig(fig, "fig_ext_health_correlation")


def compare_scheduling_objectives(df_moer, df_health, recompute=False):
    print("\n── Scheduling objective comparison ──")
    cache_tag = "ext_health_sched"
    if not recompute:
        cached = load_cache(cache_tag, {"v": 3})
        if cached is not None: return cached
    ji = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    tl_key = f"tl_{TL_STRATEGY}_moer"
    moer_win = df_moer[(df_moer["region"]==HEALTH_REGION)&(df_moer["hour"]>=DAY_SHIFT_START)&(df_moer["hour"]<DAY_SHIFT_END)].sort_values("point_time_local")
    health_win = df_health[(df_health["hour"]>=DAY_SHIFT_START)&(df_health["hour"]<DAY_SHIFT_END)].sort_values("point_time_local")
    mgt = moer_win["value"].quantile(GREEN_PERCENTILE/100); mrt = moer_win["value"].quantile(RED_PERCENTILE/100)
    hgt = health_win["value"].quantile(GREEN_PERCENTILE/100); hrt = health_win["value"].quantile(RED_PERCENTILE/100)
    results = []
    for date in sorted(set(moer_win["date"].unique()) & set(health_win["date"].unique())):
        mv = moer_win[moer_win["date"]==date].sort_values("point_time_local")["value"].values
        hv = health_win[health_win["date"]==date].sort_values("point_time_local")["value"].values
        ml = min(len(mv),len(hv)); mv,hv = mv[:ml],hv[:ml]
        if ml < ji: continue
        nw = ml - ji + 1
        # MOER TL pick
        msm = mv[:nw]; mgm = msm<=mgt; mym = (msm>mgt)&(msm<mrt)
        midx = np.where(mgm)[0][0] if np.any(mgm) else (np.where(mym)[0][0] if np.any(mym) else 0)
        # Health TL pick
        hsm = hv[:nw]; hgm = hsm<=hgt; hym = (hsm>hgt)&(hsm<hrt)
        hidx = np.where(hgm)[0][0] if np.any(hgm) else (np.where(hym)[0][0] if np.any(hym) else 0)
        results.append({
            "date": date,
            "moer_baseline": float(np.mean(mv)),  "health_baseline": float(np.mean(hv)),
            "moer_at_moer_opt":   float(np.mean(mv[midx:midx+ji])),
            "health_at_moer_opt": float(np.mean(hv[midx:midx+ji])),
            "moer_at_health_opt":   float(np.mean(mv[hidx:hidx+ji])),
            "health_at_health_opt": float(np.mean(hv[hidx:hidx+ji])),
            "same_pick": abs(midx-hidx) <= INTERVALS_PER_HOUR,
        })
    df = pd.DataFrame(results)
    if len(df)>0: save_cache(df, cache_tag, {"v": 3})
    return df


def plot_scheduling_comparison(sched_df):
    print("\n── Fig: Scheduling comparison ──")
    if len(sched_df)==0: print("  ⚠️ No data"); return
    mb,hb = sched_df["moer_baseline"], sched_df["health_baseline"]
    ms_m = ((mb-sched_df["moer_at_moer_opt"])/mb*100).mean()
    ms_h = ((mb-sched_df["moer_at_health_opt"])/mb*100).mean()
    hs_h = ((hb-sched_df["health_at_health_opt"])/hb*100).mean()
    hs_m = ((hb-sched_df["health_at_moer_opt"])/hb*100).mean()
    hcap = hs_m/hs_h*100 if hs_h>0 else 100
    agr = sched_df["same_pick"].mean()*100
    record_number("Health","MOER savings from MOER-opt %",ms_m,".1f")
    record_number("Health","Health savings from MOER-opt %",hs_m,".1f")
    record_number("Health","Health capture from carbon scheduling %",hcap,".0f")
    record_number("Health","% days same window",agr,".0f")
    with thesis_style():
        fig, ax = plt.subplots(figsize=(8, 5))
        cats = ["CO₂ Savings","Health Damage\nSavings"]; x = np.arange(2); w=0.35
        ax.bar(x-w/2,[ms_m,hs_m],w,label="Optimize for CO₂",color="#4575b4",edgecolor="white")
        ax.bar(x+w/2,[ms_h,hs_h],w,label="Optimize for Health",color="#d73027",edgecolor="white")
        ax.set_xticks(x); ax.set_xticklabels(cats,fontsize=11); ax.set_ylabel("Savings (%)")
        ax.legend(fontsize=10); ax.set_ylim(bottom=0)
        ax.text(0.5,0.95,f"Carbon scheduling captures {hcap:.0f}% of health benefit\n({agr:.0f}% same window)",
                transform=ax.transAxes,fontsize=10,ha="center",va="top",bbox=dict(boxstyle="round",facecolor="lightyellow",alpha=0.8))
        save_fig(fig, "fig_ext_health_scheduling")
    save_table(pd.DataFrame([
        {"Objective":"Minimize CO₂","CO₂ Savings (%)":round(ms_m,1),"Health Savings (%)":round(hs_m,1)},
        {"Objective":"Minimize Health","CO₂ Savings (%)":round(ms_h,1),"Health Savings (%)":round(hs_h,1)},
    ]), "table_ext_health_cobenefits","Scheduling outcomes by objective (CAISO_NORTH).")


def main(recompute=False):
    init()
    df_moer = load_5min()
    df_health = load_health_data()
    if df_health is None:
        print("\n⚠️ Health damage data not available. Skipping.")
        export_numbers(); return
    overlap = set(df_moer[df_moer["region"]==HEALTH_REGION]["date"].unique()) & set(df_health["date"].unique())
    print(f"  Date overlap: {len(overlap)} days")
    if len(overlap)<30: print("  ⚠️ <30 days overlap — results may be unreliable")
    mh, hh, corr = compute_diurnal_comparison(df_moer, df_health)
    plot_diurnal_comparison(mh, hh, corr)
    corr_df = compute_hourly_correlation(df_moer, df_health)
    plot_hourly_correlation(corr_df)
    sched_df = compare_scheduling_objectives(df_moer, df_health, recompute=recompute)
    plot_scheduling_comparison(sched_df)
    export_numbers()
    print("\n✅ Health co-benefits analysis complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)
