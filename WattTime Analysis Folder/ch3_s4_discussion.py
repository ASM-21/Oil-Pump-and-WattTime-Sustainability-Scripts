"""
ch3_s4_discussion.py — Section 3.6 figures and tables.

Outputs:
    Tables:
        table_3_7_maintenance_timing.csv/md  — Shutdown month / production month recs
    Analysis:
        Weekend vs weekday savings (CAISO and others)
        Oil pump retrospective (STUB — requires Ch2 data)

Usage:
    python ch3_s4_discussion.py
    python ch3_s4_discussion.py --recompute
"""

import argparse
import numpy as np
import pandas as pd

from ch3_common import (
    init, thesis_style, save_fig, save_table, record_number, export_numbers,
    load_5min, load_hourly,
    run_scheduling_sim, compute_thresholds, simulate_day,
    CH3_REGIONS, SIGNAL_UNIT,
    DAY_SHIFT_START, DAY_SHIFT_END, REFERENCE_JOB_HOURS, INTERVALS_PER_HOUR,
    TL_STRATEGY, ALL_TL_STRATEGIES,
    rshort, rcolor,
    FIGURES_DIR,
)


# =============================================================================
# TABLE 3-7: MAINTENANCE SHUTDOWN / PRODUCTION TIMING
# =============================================================================

def build_table_3_7(df_hourly: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly MOER rankings per region.
    Shutdown month = highest average MOER (best to be offline).
    Production month = lowest average MOER (cheapest carbon).
    MOER gap = % difference between worst and best months.
    """
    print("\n── Table 3-7: Maintenance shutdown and production timing ──")
    
    rows = []
    
    for region in CH3_REGIONS:
        rd = df_hourly[df_hourly["region"] == region]
        if len(rd) == 0:
            continue
        
        monthly = rd.groupby("month")["value_mean"].mean()
        
        worst_month = monthly.idxmax()
        best_month  = monthly.idxmin()
        gap_pct     = (monthly.max() - monthly.min()) / monthly.mean() * 100
        
        month_names = {1: "January", 2: "February", 3: "March", 4: "April",
                       5: "May", 6: "June", 7: "July", 8: "August",
                       9: "September", 10: "October", 11: "November", 12: "December"}
        
        rows.append({
            "Archetype":       CH3_REGIONS[region]["archetype"],
            "Region":          rshort(region),
            "Shutdown Month":  month_names[worst_month],
            "Production Month": month_names[best_month],
            "MOER Gap (%)":    round(gap_pct, 1),
        })
        
        record_number("Table 3-7",
                      f"{rshort(region)} shutdown month", month_names[worst_month])
        record_number("Table 3-7",
                      f"{rshort(region)} production month", month_names[best_month])
        record_number("Table 3-7",
                      f"{rshort(region)} monthly MOER gap %", gap_pct, ".1f")
    
    table = pd.DataFrame(rows)
    save_table(table, "table_3_7_maintenance_timing",
               "Table 3-7. Maintenance shutdown and production timing recommendations by archetype.")
    return table


# =============================================================================
# WEEKEND VS WEEKDAY ANALYSIS
# =============================================================================

def analyze_weekend_effect(
    df_5min: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compare TL savings on weekdays vs weekends for each region.
    Referenced in Section 3.6.2 (CAISO 30.8% weekend vs 23.0% weekday).
    """
    print("\n── Weekend vs weekday savings ──")
    
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    thresh_dict = {
        row["region"]: (row["green_threshold"], row["red_threshold"])
        for _, row in thresholds.iterrows()
    }
    tl_key = f"tl_{TL_STRATEGY}_moer"
    
    results = []
    
    for region in CH3_REGIONS:
        if region not in thresh_dict:
            continue
        green_t, red_t = thresh_dict[region]
        
        rd = df_5min[
            (df_5min["region"] == region) &
            (df_5min["hour"] >= DAY_SHIFT_START) &
            (df_5min["hour"] < DAY_SHIFT_END)
        ]
        
        for is_weekend in [False, True]:
            subset = rd[rd["is_weekend"] == is_weekend]
            day_type = "weekend" if is_weekend else "weekday"
            
            daily_savings = []
            for _, day_df in subset.groupby("date"):
                day_df = day_df.sort_values("point_time_local")
                vals = day_df["value"].values
                if len(vals) < job_intervals:
                    continue
                # FIX: removed day_hours arg; use tl_key instead of traffic_light_moer
                result = simulate_day(vals, job_intervals, green_t, red_t)
                if result:
                    base = result["baseline_moer"]
                    tl   = result[tl_key]
                    if base > 0:
                        daily_savings.append((base - tl) / base * 100)
            
            if daily_savings:
                mean_sav = np.mean(daily_savings)
                results.append({
                    "region":    region,
                    "day_type":  day_type,
                    "mean_tl_savings_pct": mean_sav,
                    "n_days":    len(daily_savings),
                })
                record_number("Section 3.6.2",
                              f"{rshort(region)} {day_type} TL savings %",
                              mean_sav, ".1f")
    
    wk_df = pd.DataFrame(results)
    
    # Compute weekend improvement for CAISO
    caiso = wk_df[wk_df["region"] == "CAISO_NORTH"]
    if len(caiso) == 2:
        wd = caiso[caiso["day_type"] == "weekday"]["mean_tl_savings_pct"].values[0]
        we = caiso[caiso["day_type"] == "weekend"]["mean_tl_savings_pct"].values[0]
        improvement = (we - wd) / wd * 100 if wd > 0 else 0
        record_number("Section 3.6.2", "CAISO weekend improvement %",
                      improvement, ".0f")
    
    save_table(wk_df, "weekend_vs_weekday",
               "Weekend vs weekday traffic light savings by region.")
    return wk_df


# =============================================================================
# OIL PUMP RETROSPECTIVE — STUB
# =============================================================================

def oil_pump_retrospective_stub():
    """
    Placeholder for the oil pump retrospective analysis (Section 3.6.3).
    
    This analysis joins Chapter 2 machining timestamps + power data with
    MISO MOER data to compute:
      1. Actual CO₂e from real production timestamps
      2. Counterfactual CO₂e if jobs had been scheduled in green windows
      3. Per-part and annual savings estimates
    
    Required inputs (not yet available in this project):
      - Ch2 UUID-tagged power profiles (1 Hz, per operation)
      - Ch2 machining timestamps (start/end per operation per part)
      - MISO_INDIANAPOLIS 5-min MOER data (already in processed parquet)
    
    Expected outputs:
      - Actual vs green-window CO₂e per part
      - Savings % consistent with ~4% traffic light savings for MISO
      - Annual tonnage estimate at 100 parts/day × 250 days
    
    To implement:
      1. Load Ch2 power profiles and timestamps
      2. For each operation, compute actual_co2e = Σ P(t) × MOER(t) × Δt
      3. For counterfactual, find the green window on the same day that
         minimizes the integral
      4. Aggregate across all parts in the dataset
    """
    print("\n── Oil pump retrospective (STUB) ──")
    print("  ⚠️  This analysis requires Chapter 2 power/timestamp data.")
    print("  ⚠️  Populate this function when Ch2 data is accessible.")
    print()
    
    # Record placeholder numbers from chapter draft for tracking
    record_number("Section 3.6.3", "MISO TL savings (from Table 3-5)", "~4.0%")
    record_number("Section 3.6.3", "Avg CNC energy per oil pump (Ch2)", "0.755 kWh")
    record_number("Section 3.6.3",
                  "Estimated annual CNC savings at 100 parts/day",
                  "0.5–0.75 tonnes CO₂e")
    
    print("  💡 To implement, provide path to Ch2 data and call with:")
    print("     oil_pump_retrospective(ch2_power_path, ch2_timestamps_path)")


# =============================================================================
# SHIFT ANALYSIS (supplementary, referenced in Section 3.5.3 text)
# =============================================================================

def analyze_shift_capture(
    df_5min: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute TL savings for each shift window (1st, 2nd, 3rd) per region.
    Referenced in Section 3.5.3 — the 55%/72%/33% capture rates.
    """
    print("\n── Shift-constrained savings ──")
    
    shifts = {
        "1st (07-15)": (7, 15),
        "2nd (15-23)": (15, 23),
        "3rd (23-07)": (23, 7),  # crosses midnight
    }
    
    job_intervals = int(REFERENCE_JOB_HOURS * INTERVALS_PER_HOUR)
    thresh_dict = {
        row["region"]: (row["green_threshold"], row["red_threshold"])
        for _, row in thresholds.iterrows()
    }
    tl_key = f"tl_{TL_STRATEGY}_moer"
    
    # First get unconstrained savings (06-18 window)
    unconstrained_sim = run_scheduling_sim(
        df_5min, thresholds=thresholds,
        use_cache=True, cache_tag="s4_unconstrained",
    )
    unconstrained_by_region = unconstrained_sim.groupby("region")["savings_tl_pct"].mean()
    
    results = []
    
    for shift_name, (s_start, s_end) in shifts.items():
        for region in CH3_REGIONS:
            if region not in thresh_dict:
                continue
            green_t, red_t = thresh_dict[region]
            
            rd = df_5min[df_5min["region"] == region].copy()
            
            # Handle midnight-crossing shift
            if s_start > s_end:
                shift_data = rd[(rd["hour"] >= s_start) | (rd["hour"] < s_end)]
            else:
                shift_data = rd[(rd["hour"] >= s_start) & (rd["hour"] < s_end)]
            
            daily_savings = []
            for _, day_df in shift_data.groupby("date"):
                day_df = day_df.sort_values("point_time_local")
                vals = day_df["value"].values
                if len(vals) < job_intervals:
                    continue
                # FIX: removed day_hours arg; use tl_key instead of traffic_light_moer
                result = simulate_day(vals, job_intervals, green_t, red_t)
                if result and result["baseline_moer"] > 0:
                    base = result["baseline_moer"]
                    tl   = result[tl_key]
                    daily_savings.append((base - tl) / base * 100)
            
            if daily_savings:
                shift_sav = np.mean(daily_savings)
                uncon = unconstrained_by_region.get(region, 1)
                capture = shift_sav / uncon * 100 if uncon > 0 else 100
                
                results.append({
                    "shift":             shift_name,
                    "region":            region,
                    "shift_savings_pct": shift_sav,
                    "unconstrained_pct": uncon,
                    "capture_of_unconstrained_pct": capture,
                })
    
    shift_df = pd.DataFrame(results)
    
    # Summary by shift
    if len(shift_df) > 0:
        shift_summary = shift_df.groupby("shift")["capture_of_unconstrained_pct"].mean()
        for shift, cap in shift_summary.items():
            record_number("Section 3.5.3", f"{shift} capture of unconstrained %",
                          cap, ".0f")
        # Overall mean TL savings by shift (across all regions)
        shift_mean_sav = shift_df.groupby("shift")["shift_savings_pct"].mean()
        for shift, sav in shift_mean_sav.items():
            record_number("Section 3.5.3", f"{shift} mean TL savings %",
                          sav, ".1f")
    
    save_table(shift_df, "shift_constrained_savings",
               "Shift-constrained traffic light savings by region.")
    return shift_df


# =============================================================================
# MAIN
# =============================================================================

def main(recompute: bool = False):
    init()
    
    df_5min   = load_5min()
    df_hourly = load_hourly()
    thresholds = compute_thresholds(df_5min)
    
    # --- Table 3-7: maintenance timing ---
    build_table_3_7(df_hourly)
    
    # --- Weekend effect ---
    analyze_weekend_effect(df_5min, thresholds)
    
    # --- Shift capture (supplementary for Section 3.5.3) ---
    analyze_shift_capture(df_5min, thresholds)
    
    # --- Oil pump retrospective stub ---
    oil_pump_retrospective_stub()
    
    export_numbers()
    print("\n✅ Section 3.6 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recompute", action="store_true")
    args = parser.parse_args()
    main(recompute=args.recompute)