"""
00_validate_data.py - Library Data Validation & Quality Audit

Two purposes:
  1. Check forecast (and historical) data COMPLETENESS per region
     → Diagnose "partial forecast data exists" errors
  2. Check data QUALITY per region
     → Flag outlier distributions (e.g. SPP_KANSAS threshold anomaly)

Usage:
    1. Edit CONFIG section below
    2. Run: python 00_validate_data.py

Output:
    - Console summary of completeness & quality
    - outputs/data_validation_report.md  (detailed report)
    - outputs/data_quality_summary.csv   (per-region stats)
    - figures/validation_distributions.png (box plots per region)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import json
import sys

# =============================================================================
# ▼▼▼ USER CONFIG - EDIT THIS SECTION ▼▼▼
# =============================================================================

# Path to your watttime_analysis project root
# (the directory containing library/, runs/, config.py)
PROJECT_ROOT = Path(__file__).parent.parent
# If running from scripts/ folder, use:
# PROJECT_ROOT = Path(__file__).parent.parent

# Signal to validate
SIGNAL = "co2_moer"

# Regions to validate - list or group name
# Set to None to auto-detect all regions with data in library
REGIONS_TO_VALIDATE = [
    "CAISO_NORTH",
    "SPP_KANSAS",
    "BPA",
    "MISO_INDIANAPOLIS",
    "ISONE_CT",
    "ERCOT_NORTHCENTRAL",
]

# Data types to check
DATA_TYPES_TO_CHECK = ["historical", "forecast"]

# Expected date range
EXPECTED_START = datetime(2022, 1, 1)
EXPECTED_END = datetime(2024, 12, 31)

# Where to save outputs (set to None to skip file outputs)
OUTPUT_DIR = Path(__file__).parent / "validation_outputs"

# =============================================================================
# ▲▲▲ END USER CONFIG ▲▲▲
# =============================================================================

# Derived paths
LIBRARY_DIR = PROJECT_ROOT / "library"


def find_library_file(signal: str, region: str, data_type: str) -> Optional[Path]:
    """Locate a parquet file in the library."""
    path = LIBRARY_DIR / signal / data_type / f"{region}.parquet"
    if path.exists():
        return path
    return None


def auto_detect_regions(signal: str, data_type: str) -> List[str]:
    """Find all regions with data files for a signal/data_type."""
    data_dir = LIBRARY_DIR / signal / data_type
    if not data_dir.exists():
        return []
    return sorted([f.stem for f in data_dir.glob("*.parquet")])


# ─────────────────────────────────────────────────────────────
# PART 1: COMPLETENESS CHECK
# ─────────────────────────────────────────────────────────────

def check_completeness(
    signal: str,
    region: str,
    data_type: str,
    expected_start: datetime,
    expected_end: datetime,
) -> Dict:
    """
    Check data completeness for one region/data_type.
    Returns a dict of metrics.
    """
    result = {
        "region": region,
        "data_type": data_type,
        "file_exists": False,
        "n_records": 0,
        "actual_start": None,
        "actual_end": None,
        "expected_days": (expected_end - expected_start).days + 1,
        "days_with_data": 0,
        "days_missing": 0,
        "completeness_pct": 0.0,
        "missing_months": [],
        "gap_summary": [],
        "status": "MISSING",
    }

    file_path = find_library_file(signal, region, data_type)
    if file_path is None:
        return result

    result["file_exists"] = True

    try:
        df = pd.read_parquet(file_path)
    except Exception as e:
        result["status"] = f"READ_ERROR: {e}"
        return result

    if len(df) == 0:
        result["status"] = "EMPTY_FILE"
        return result

    result["n_records"] = len(df)

    # Parse timestamps
    df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
    result["actual_start"] = df["point_time"].min()
    result["actual_end"] = df["point_time"].max()

    # Daily coverage analysis
    df["date"] = df["point_time"].dt.date
    unique_dates = set(df["date"].unique())

    # Expected dates
    all_expected_dates = set()
    d = expected_start.date()
    while d <= expected_end.date():
        all_expected_dates.add(d)
        d += timedelta(days=1)

    covered_dates = unique_dates & all_expected_dates
    missing_dates = all_expected_dates - unique_dates

    result["days_with_data"] = len(covered_dates)
    result["days_missing"] = len(missing_dates)
    result["completeness_pct"] = 100.0 * len(covered_dates) / len(all_expected_dates) if all_expected_dates else 0

    # Identify missing months
    if missing_dates:
        missing_months = set()
        for d in missing_dates:
            missing_months.add(f"{d.year}-{d.month:02d}")
        result["missing_months"] = sorted(missing_months)

    # Identify contiguous gaps
    if missing_dates:
        sorted_missing = sorted(missing_dates)
        gaps = []
        gap_start = sorted_missing[0]
        prev = sorted_missing[0]
        for d in sorted_missing[1:]:
            if (d - prev).days > 1:
                gaps.append((gap_start, prev, (prev - gap_start).days + 1))
                gap_start = d
            prev = d
        gaps.append((gap_start, prev, (prev - gap_start).days + 1))
        # Summarize top gaps
        gaps.sort(key=lambda x: x[2], reverse=True)
        result["gap_summary"] = [
            {"start": str(g[0]), "end": str(g[1]), "days": g[2]}
            for g in gaps[:10]  # top 10 gaps
        ]

    # Determine status
    if result["completeness_pct"] >= 99.0:
        result["status"] = "COMPLETE"
    elif result["completeness_pct"] >= 80.0:
        result["status"] = "PARTIAL"
    elif result["completeness_pct"] > 0:
        result["status"] = "SPARSE"
    else:
        result["status"] = "NO_COVERAGE"

    # Forecast-specific: check generated_at coverage
    if data_type == "forecast" and "generated_at" in df.columns:
        df["generated_at"] = pd.to_datetime(df["generated_at"], utc=True)
        df["gen_date"] = df["generated_at"].dt.date
        gen_dates = set(df["gen_date"].unique())
        gen_covered = gen_dates & all_expected_dates
        result["forecast_gen_dates"] = len(gen_covered)
        result["forecast_gen_completeness_pct"] = (
            100.0 * len(gen_covered) / len(all_expected_dates) if all_expected_dates else 0
        )
        
        # Check for forecast that only has point_time coverage but not generated_at coverage
        # This can happen if forecasts were fetched for future periods but not historical generated_at
        if result["forecast_gen_completeness_pct"] < result["completeness_pct"] * 0.5:
            result["status"] += " (GENERATED_AT_GAPS)"

    # 5-minute interval check for historical
    if data_type == "historical":
        # Expected: 288 intervals per day
        intervals_per_day = df.groupby("date").size()
        result["avg_intervals_per_day"] = intervals_per_day.mean()
        result["min_intervals_per_day"] = intervals_per_day.min()
        result["days_below_200_intervals"] = (intervals_per_day < 200).sum()

    return result


# ─────────────────────────────────────────────────────────────
# PART 2: DATA QUALITY CHECK
# ─────────────────────────────────────────────────────────────

def check_quality(signal: str, region: str) -> Dict:
    """
    Check data quality for historical data in one region.
    Returns distribution stats and flags anomalies.
    """
    result = {
        "region": region,
        "n_records": 0,
        "mean": None,
        "std": None,
        "min": None,
        "p01": None,
        "p05": None,
        "p10": None,
        "p25": None,
        "median": None,
        "p75": None,
        "p90": None,
        "p95": None,
        "p99": None,
        "max": None,
        "iqr": None,
        "cv": None,
        "skewness": None,
        "kurtosis": None,
        "n_zeros": 0,
        "n_negative": 0,
        "pct_below_typical_min": 0,
        "pct_above_typical_max": 0,
        "flags": [],
    }

    file_path = find_library_file(signal, region, "historical")
    if file_path is None:
        result["flags"].append("NO_HISTORICAL_DATA")
        return result

    df = pd.read_parquet(file_path)
    if len(df) == 0:
        result["flags"].append("EMPTY_FILE")
        return result

    values = df["value"].dropna()
    result["n_records"] = len(values)

    if len(values) == 0:
        result["flags"].append("ALL_NULL_VALUES")
        return result

    # Distribution stats
    result["mean"] = values.mean()
    result["std"] = values.std()
    result["min"] = values.min()
    result["p01"] = values.quantile(0.01)
    result["p05"] = values.quantile(0.05)
    result["p10"] = values.quantile(0.10)
    result["p25"] = values.quantile(0.25)
    result["median"] = values.median()
    result["p75"] = values.quantile(0.75)
    result["p90"] = values.quantile(0.90)
    result["p95"] = values.quantile(0.95)
    result["p99"] = values.quantile(0.99)
    result["max"] = values.max()
    result["iqr"] = result["p75"] - result["p25"]
    result["cv"] = result["std"] / result["mean"] if result["mean"] != 0 else None
    result["skewness"] = values.skew()
    result["kurtosis"] = values.kurtosis()

    # Anomaly flags
    result["n_zeros"] = (values == 0).sum()
    result["n_negative"] = (values < 0).sum()

    typical_range = {
        "co2_moer": (200, 2500),
        "co2_aoer": (200, 2000),
        "health_damage": (0, 200),
    }.get(signal, (0, 5000))

    result["pct_below_typical_min"] = 100.0 * (values < typical_range[0]).sum() / len(values)
    result["pct_above_typical_max"] = 100.0 * (values > typical_range[1]).sum() / len(values)

    # Flag specific issues
    if result["n_negative"] > 0:
        result["flags"].append(f"NEGATIVE_VALUES ({result['n_negative']})")

    if result["cv"] and result["cv"] > 1.5:
        result["flags"].append(f"HIGH_CV ({result['cv']:.2f})")

    if result["skewness"] and abs(result["skewness"]) > 3:
        result["flags"].append(f"EXTREME_SKEW ({result['skewness']:.2f})")

    if result["max"] and result["mean"] and result["max"] > 10 * result["mean"]:
        result["flags"].append(f"EXTREME_OUTLIERS (max={result['max']:.0f}, mean={result['mean']:.0f})")

    if result["pct_below_typical_min"] > 5:
        result["flags"].append(f"MANY_LOW_VALUES ({result['pct_below_typical_min']:.1f}%)")

    if result["pct_above_typical_max"] > 5:
        result["flags"].append(f"MANY_HIGH_VALUES ({result['pct_above_typical_max']:.1f}%)")

    # Check for threshold anomaly (the SPP Kansas issue)
    # If p25 is very low relative to p75, the "green" threshold will be very low
    # while "yellow" spans a huge range
    if result["iqr"] and result["p25"]:
        green_yellow_ratio = result["p25"] / result["p75"] if result["p75"] else 0
        if green_yellow_ratio < 0.15:
            result["flags"].append(
                f"THRESHOLD_ANOMALY: p25={result['p25']:.0f} vs p75={result['p75']:.0f} "
                f"(ratio={green_yellow_ratio:.3f}) — green band very narrow"
            )

    # Seasonal consistency check
    df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
    df["month"] = df["point_time"].dt.month
    monthly_means = df.groupby("month")["value"].mean()
    if len(monthly_means) >= 6:
        seasonal_cv = monthly_means.std() / monthly_means.mean() if monthly_means.mean() != 0 else 0
        result["seasonal_cv"] = seasonal_cv
        if seasonal_cv > 0.5:
            result["flags"].append(f"HIGH_SEASONAL_VARIATION (cv={seasonal_cv:.2f})")

    return result


# ─────────────────────────────────────────────────────────────
# VISUALIZATION
# ─────────────────────────────────────────────────────────────

def plot_distributions(signal: str, regions: List[str], output_dir: Path):
    """Box plots of value distributions across regions for visual comparison."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Collect data
    data_for_box = {}
    for region in regions:
        file_path = find_library_file(signal, region, "historical")
        if file_path and file_path.exists():
            df = pd.read_parquet(file_path)
            if len(df) > 0:
                data_for_box[region] = df["value"].dropna().values

    if not data_for_box:
        print("  No historical data to plot")
        plt.close()
        return

    # Left: full box plots
    ax1 = axes[0]
    bp_data = [data_for_box[r] for r in data_for_box]
    bp_labels = list(data_for_box.keys())
    bp = ax1.boxplot(bp_data, labels=bp_labels, vert=True, patch_artist=True,
                     showfliers=False, widths=0.6)
    colors = plt.cm.Set2(np.linspace(0, 1, len(bp_labels)))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax1.set_ylabel("lbs CO₂/MWh")
    ax1.set_title(f"{signal} Distribution by Region (no outliers)")
    ax1.tick_params(axis="x", rotation=45)
    ax1.grid(True, alpha=0.3, axis="y")

    # Right: violin plots to show shape
    ax2 = axes[1]
    # Subsample for violin performance
    violin_data = []
    for r in data_for_box:
        vals = data_for_box[r]
        if len(vals) > 50000:
            vals = np.random.choice(vals, 50000, replace=False)
        violin_data.append(vals)
    
    vp = ax2.violinplot(violin_data, showmedians=True, showextremes=False)
    for i, body in enumerate(vp["bodies"]):
        body.set_facecolor(colors[i])
        body.set_alpha(0.7)
    ax2.set_xticks(range(1, len(bp_labels) + 1))
    ax2.set_xticklabels(bp_labels, rotation=45)
    ax2.set_ylabel("lbs CO₂/MWh")
    ax2.set_title(f"{signal} Distribution Shape (violin)")
    ax2.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_dir / "validation_distributions.png", dpi=150)
    plt.close()
    print(f"  Saved: validation_distributions.png")


def plot_completeness_heatmap(
    completeness_results: List[Dict], 
    expected_start: datetime,
    expected_end: datetime,
    signal: str,
    output_dir: Path
):
    """Monthly completeness heatmap per region."""
    # Build monthly grid
    months = []
    d = expected_start.replace(day=1)
    while d <= expected_end:
        months.append(d.strftime("%Y-%m"))
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1)
        else:
            d = d.replace(month=d.month + 1)

    historical = [r for r in completeness_results if r["data_type"] == "historical"]
    forecast = [r for r in completeness_results if r["data_type"] == "forecast"]

    for dtype_label, results in [("Historical", historical), ("Forecast", forecast)]:
        if not results:
            continue

        regions = [r["region"] for r in results]
        
        # Build a matrix: region x month → completeness
        matrix = np.full((len(regions), len(months)), np.nan)
        
        for i, res in enumerate(results):
            if not res["file_exists"]:
                matrix[i, :] = 0
                continue
                
            file_path = find_library_file(signal, res["region"], res["data_type"])
            if file_path is None:
                continue
            df = pd.read_parquet(file_path)
            if len(df) == 0:
                matrix[i, :] = 0
                continue
            
            df["point_time"] = pd.to_datetime(df["point_time"], utc=True)
            df["month_str"] = df["point_time"].dt.strftime("%Y-%m")
            monthly_counts = df.groupby("month_str").size()
            
            for j, m in enumerate(months):
                if m in monthly_counts.index:
                    # Rough expected: ~8640 for 5-min historical, variable for forecast
                    expected = 8640 if res["data_type"] == "historical" else monthly_counts.get(m, 0)
                    actual = monthly_counts[m]
                    if res["data_type"] == "historical":
                        matrix[i, j] = min(100, 100 * actual / expected)
                    else:
                        matrix[i, j] = 100 if actual > 0 else 0
                else:
                    matrix[i, j] = 0

        fig, ax = plt.subplots(figsize=(max(14, len(months) * 0.5), max(4, len(regions) * 0.6)))
        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=90, fontsize=7)
        ax.set_yticks(range(len(regions)))
        ax.set_yticklabels(regions, fontsize=9)
        ax.set_title(f"{dtype_label} Data Completeness — {signal}")
        plt.colorbar(im, ax=ax, label="Completeness %", shrink=0.8)
        plt.tight_layout()
        
        fname = f"validation_completeness_{dtype_label.lower()}.png"
        output_dir.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_dir / fname, dpi=150)
        plt.close()
        print(f"  Saved: {fname}")


# ─────────────────────────────────────────────────────────────
# REPORT GENERATION
# ─────────────────────────────────────────────────────────────

def generate_report(
    completeness_results: List[Dict],
    quality_results: List[Dict],
    output_dir: Path,
):
    """Generate a markdown validation report."""
    lines = []
    lines.append("# Data Validation Report")
    lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Signal: {SIGNAL}")
    lines.append(f"Expected range: {EXPECTED_START.date()} to {EXPECTED_END.date()}")

    # ── Completeness ──
    lines.append("\n## 1. Data Completeness\n")

    for dtype in DATA_TYPES_TO_CHECK:
        dtype_results = [r for r in completeness_results if r["data_type"] == dtype]
        if not dtype_results:
            continue

        lines.append(f"\n### {dtype.capitalize()}\n")
        lines.append("| Region | Status | Records | Days w/ Data | Missing Days | Completeness | Largest Gap |")
        lines.append("|--------|--------|---------|--------------|--------------|--------------|-------------|")

        for r in dtype_results:
            largest_gap = ""
            if r["gap_summary"]:
                g = r["gap_summary"][0]
                largest_gap = f"{g['start']} to {g['end']} ({g['days']}d)"

            lines.append(
                f"| {r['region']} | {r['status']} | {r['n_records']:,} | "
                f"{r['days_with_data']} | {r['days_missing']} | "
                f"{r['completeness_pct']:.1f}% | {largest_gap} |"
            )

        # Forecast-specific: generated_at coverage
        if dtype == "forecast":
            has_gen = [r for r in dtype_results if "forecast_gen_completeness_pct" in r]
            if has_gen:
                lines.append(f"\n**Forecast generated_at coverage:**\n")
                for r in has_gen:
                    lines.append(
                        f"- {r['region']}: {r.get('forecast_gen_completeness_pct', 0):.1f}% "
                        f"of days have forecast generation timestamps "
                        f"({r.get('forecast_gen_dates', 0)} days)"
                    )

    # ── Quality ──
    lines.append("\n## 2. Data Quality\n")
    lines.append("| Region | Records | Mean | Std | Min | P25 | Median | P75 | Max | CV | Skew | Flags |")
    lines.append("|--------|---------|------|-----|-----|-----|--------|-----|-----|------|------|-------|")

    for r in quality_results:
        flags_str = "; ".join(r["flags"]) if r["flags"] else "OK"
        lines.append(
            f"| {r['region']} | {r['n_records']:,} | "
            f"{r['mean']:.0f} | {r['std']:.0f} | {r['min']:.0f} | "
            f"{r['p25']:.0f} | {r['median']:.0f} | {r['p75']:.0f} | {r['max']:.0f} | "
            f"{r['cv']:.2f} | {r['skewness']:.2f} | {flags_str} |"
        ) if r["mean"] is not None else lines.append(
            f"| {r['region']} | {r['n_records']} | — | — | — | — | — | — | — | — | — | {flags_str} |"
        )

    # ── Threshold impact analysis ──
    lines.append("\n## 3. Threshold Impact Analysis\n")
    lines.append("How percentile-based thresholds (p25/p75) translate to traffic-light cutoffs:\n")
    lines.append("| Region | Green (≤p25) | Yellow (p25-p75) | Red (>p75) | Yellow Band Width | Flag |")
    lines.append("|--------|-------------|-----------------|-----------|-------------------|------|")

    for r in quality_results:
        if r["p25"] is None:
            continue
        yellow_width = r["p75"] - r["p25"]
        ratio = r["p25"] / r["p75"] if r["p75"] > 0 else 0
        flag = "⚠️ ANOMALOUS" if ratio < 0.15 else "OK"
        lines.append(
            f"| {r['region']} | ≤{r['p25']:.0f} | {r['p25']:.0f}–{r['p75']:.0f} | "
            f">{r['p75']:.0f} | {yellow_width:.0f} | {flag} |"
        )

    # ── Recommendations ──
    lines.append("\n## 4. Recommendations\n")

    incomplete_forecast = [
        r for r in completeness_results
        if r["data_type"] == "forecast" and r["completeness_pct"] < 95
    ]
    if incomplete_forecast:
        lines.append("### Forecast Re-collection Needed\n")
        for r in incomplete_forecast:
            lines.append(
                f"- **{r['region']}**: {r['completeness_pct']:.1f}% complete, "
                f"{r['days_missing']} days missing"
            )
            if r["missing_months"]:
                lines.append(f"  - Missing months: {', '.join(r['missing_months'][:12])}")
                if len(r["missing_months"]) > 12:
                    lines.append(f"  - ... and {len(r['missing_months']) - 12} more")

    flagged_quality = [r for r in quality_results if r["flags"]]
    if flagged_quality:
        lines.append("\n### Quality Flags to Investigate\n")
        for r in flagged_quality:
            lines.append(f"- **{r['region']}**: {'; '.join(r['flags'])}")

    report_text = "\n".join(lines)

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "data_validation_report.md", "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"\n  Saved: data_validation_report.md")

    return report_text


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DATA VALIDATION & QUALITY AUDIT")
    print("=" * 60)
    print(f"Signal: {SIGNAL}")
    print(f"Library: {LIBRARY_DIR}")
    print(f"Expected range: {EXPECTED_START.date()} to {EXPECTED_END.date()}")

    # Check library exists
    if not LIBRARY_DIR.exists():
        print(f"\nERROR: Library directory not found at {LIBRARY_DIR}")
        print("Make sure PROJECT_ROOT points to your watttime_analysis folder.")
        sys.exit(1)

    # Determine regions
    if REGIONS_TO_VALIDATE:
        regions = REGIONS_TO_VALIDATE
    else:
        # Auto-detect from library
        hist_regions = auto_detect_regions(SIGNAL, "historical")
        fc_regions = auto_detect_regions(SIGNAL, "forecast")
        regions = sorted(set(hist_regions) | set(fc_regions))
        print(f"Auto-detected {len(regions)} regions with data")

    print(f"Regions: {', '.join(regions)}")
    print(f"Data types: {', '.join(DATA_TYPES_TO_CHECK)}")
    print("=" * 60)

    # ── Part 1: Completeness ──
    print("\n─── COMPLETENESS CHECK ───")
    completeness_results = []
    for dtype in DATA_TYPES_TO_CHECK:
        print(f"\n  Checking {dtype} data...")
        for region in regions:
            result = check_completeness(SIGNAL, region, dtype, EXPECTED_START, EXPECTED_END)
            completeness_results.append(result)

            status_icon = {
                "COMPLETE": "✓",
                "PARTIAL": "◐",
                "SPARSE": "○",
                "MISSING": "✗",
            }.get(result["status"].split()[0], "?")

            print(
                f"    {status_icon} {region:25s} {result['status']:15s} "
                f"{result['n_records']:>10,} records  "
                f"{result['completeness_pct']:5.1f}% complete"
            )
            if result["gap_summary"]:
                g = result["gap_summary"][0]
                print(f"      └─ Largest gap: {g['start']} to {g['end']} ({g['days']} days)")

    # ── Part 2: Quality ──
    print("\n─── QUALITY CHECK (Historical) ───")
    quality_results = []
    for region in regions:
        result = check_quality(SIGNAL, region)
        quality_results.append(result)

        if result["mean"] is not None:
            flags_str = " ⚠ " + "; ".join(result["flags"]) if result["flags"] else ""
            print(
                f"    {region:25s} "
                f"mean={result['mean']:7.0f}  std={result['std']:7.0f}  "
                f"range=[{result['min']:.0f}, {result['max']:.0f}]  "
                f"CV={result['cv']:.2f}{flags_str}"
            )
        else:
            print(f"    {region:25s} — no data")

    # ── Outputs ──
    if OUTPUT_DIR:
        print(f"\n─── GENERATING OUTPUTS ───")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Markdown report
        report = generate_report(completeness_results, quality_results, OUTPUT_DIR)

        # CSV summary
        quality_df = pd.DataFrame(quality_results)
        quality_df.to_csv(OUTPUT_DIR / "data_quality_summary.csv", index=False)
        print(f"  Saved: data_quality_summary.csv")

        completeness_df = pd.DataFrame([
            {k: v for k, v in r.items() if k not in ["gap_summary", "missing_months"]}
            for r in completeness_results
        ])
        completeness_df.to_csv(OUTPUT_DIR / "data_completeness_summary.csv", index=False)
        print(f"  Saved: data_completeness_summary.csv")

        # Plots
        print("\n  Generating plots...")
        plot_distributions(SIGNAL, regions, OUTPUT_DIR)
        plot_completeness_heatmap(
            completeness_results, EXPECTED_START, EXPECTED_END, SIGNAL, OUTPUT_DIR
        )

    # ── Final summary ──
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for dtype in DATA_TYPES_TO_CHECK:
        dtype_results = [r for r in completeness_results if r["data_type"] == dtype]
        complete = sum(1 for r in dtype_results if "COMPLETE" in r["status"])
        partial = sum(1 for r in dtype_results if "PARTIAL" in r["status"])
        missing = sum(1 for r in dtype_results if r["status"] in ("MISSING", "EMPTY_FILE"))
        print(f"\n  {dtype.capitalize()}:")
        print(f"    Complete: {complete}/{len(dtype_results)}")
        print(f"    Partial:  {partial}/{len(dtype_results)}")
        print(f"    Missing:  {missing}/{len(dtype_results)}")

    flagged = [r for r in quality_results if r["flags"]]
    if flagged:
        print(f"\n  Quality flags ({len(flagged)} regions):")
        for r in flagged:
            print(f"    {r['region']}: {'; '.join(r['flags'])}")

    if OUTPUT_DIR:
        print(f"\n  Full report: {OUTPUT_DIR / 'data_validation_report.md'}")

    print("=" * 60)


if __name__ == "__main__":
    main()
