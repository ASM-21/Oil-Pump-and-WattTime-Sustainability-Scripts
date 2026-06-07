"""
1_grafana_operator_deploy.py - Grafana Traffic Light Deployment

Generates the static artifacts needed to run a live traffic light dashboard
in Grafana for shop-floor operators. No API integration required on the
operator side — just a current MOER reading and the lookup tables produced
here.

Workflow:
    1. Run 11_threshold_buckets.py first (thresholds must exist)
    2. Edit CONFIG section (select your region)
    3. Run: python 13_grafana_operator_deploy.py
    4. Import outputs into Grafana (see README in outputs/13_grafana/)

What this generates:
    A. Threshold config  — JSON value mappings for Grafana Stat / Gauge panels
                           (MOER value → green/yellow/red color + label)
    B. Hourly lookup     — CSV and heatmap: season × hour → expected bucket
                           (operator's "expected conditions" reference)
    C. Grafana dashboard — JSON dashboard template ready to import
                           Panels: live traffic light, hourly heatmap,
                           shift summary, MOER trend with threshold bands
    D. Operator card     — Printable PNG reference card with thresholds
                           and recommended actions for each bucket

Grafana setup (after running this script):
    1. Ensure WattTime MOER data is flowing into InfluxDB / your data source
    2. In Grafana: Dashboards → Import → upload 13_grafana_dashboard.json
    3. Set your data source variable in the dashboard to match your setup
    4. The threshold values are pre-loaded from your region's MOER distribution

Output:
    outputs/13_grafana/
        thresholds_<REGION>.json
        hourly_lookup_<REGION>.csv
        13_grafana_dashboard.json
        13_operator_card.png
    figures/
        13_hourly_heatmap.png
        13_operator_reference.png
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import seaborn as sns
import json
from pathlib import Path
from datetime import datetime
from typing import Dict
import warnings
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    REGIONS, SEASONS, RUNS_DIR,
    FIGURE_DPI,
    get_signal_metadata, get_unit_label
)

warnings.filterwarnings('ignore', category=FutureWarning)

# =============================================================================
# ▼▼▼ USER CONFIG ▼▼▼
# =============================================================================

RUN_FOLDER = "2026-02-26_GridMixStudy_Test_forcast and historical"

# Region to deploy for. Operator installs one dashboard per region/facility.
# Must match a region key in your run (e.g. "MISO_INDY", "CAISO_N", "BPA")
DEPLOY_REGION = "MISO_INDY"

# Grafana data source name (must match your Grafana instance)
# This is the InfluxDB / data source name where live MOER values arrive
GRAFANA_DATASOURCE_NAME = "InfluxDB-WattTime"

# InfluxDB measurement and field names for live MOER
# Adjust to match your WattTime ingestion pipeline
INFLUX_MEASUREMENT = "moer"
INFLUX_FIELD_MOER  = "value"
INFLUX_TAG_REGION  = "region"

# Shift window shown on dashboard (24h clock)
SHIFT_START = 6
SHIFT_END   = 22

# =============================================================================
# ▲▲▲ END CONFIG ▲▲▲
# =============================================================================

TRAFFIC_COLORS_HEX = {
    "green":  "#2ecc71",
    "yellow": "#f39c12",
    "red":    "#e74c3c",
}

TRAFFIC_COLORS_GRAFANA = {
    "green":  "green",
    "yellow": "orange",
    "red":    "red",
}

BUCKET_ACTIONS = {
    "green":  "RUN — grid is clean. Schedule high-energy jobs now.",
    "yellow": "PROCEED — grid is moderate. Run if production requires.",
    "red":    "DEFER — grid is dirty. Postpone deferrable jobs if possible.",
}


# =============================================================================
# LOAD DATA
# =============================================================================

def get_run_dir() -> Path:
    if RUN_FOLDER:
        run_dir = RUNS_DIR / RUN_FOLDER
        if not run_dir.exists():
            print(f"ERROR: Run folder not found: {run_dir}")
            sys.exit(1)
        return run_dir
    runs = sorted([d for d in RUNS_DIR.iterdir() if d.is_dir()], reverse=True)
    if not runs:
        print("ERROR: No runs found.")
        sys.exit(1)
    return runs[0]


def load_thresholds(run_dir: Path) -> pd.DataFrame:
    path = run_dir / "outputs" / "11_thresholds.csv"
    if not path.exists():
        print("ERROR: 11_thresholds.csv not found. Run 11_threshold_buckets.py first.")
        sys.exit(1)
    return pd.read_csv(path)


def load_hourly(run_dir: Path) -> pd.DataFrame:
    df = pd.read_parquet(run_dir / "processed" / "data_hourly.parquet")
    df["point_time"] = pd.to_datetime(
        df[["year", "month", "day", "hour"]].assign(minute=0, second=0)
    )
    return df


def assign_buckets(df: pd.DataFrame, thresh_row: pd.Series) -> pd.DataFrame:
    df = df.copy()
    df["bucket"] = "yellow"
    df.loc[df["value_mean"] <= thresh_row["green_threshold"], "bucket"] = "green"
    df.loc[df["value_mean"] >= thresh_row["red_threshold"],   "bucket"] = "red"
    return df


# =============================================================================
# A. THRESHOLD CONFIG  →  Grafana value mappings
# =============================================================================

def build_threshold_config(thresh_row: pd.Series) -> dict:
    """
    Grafana threshold config for a Stat or Gauge panel.
    MOER value → color + label + action.
    Grafana 'thresholds' use step-based coloring from base upward.
    """
    green_val  = float(thresh_row["green_threshold"])
    red_val    = float(thresh_row["red_threshold"])
    region     = thresh_row["region"]
    region_name = thresh_row.get("region_name", region)

    config = {
        "region":       region,
        "region_name":  region_name,
        "signal":       "MOER (lbs CO\u2082/MWh)",
        "generated":    datetime.now().isoformat(),
        "buckets": {
            "green": {
                "label":     "GREEN — Run",
                "max_value": green_val,
                "color_hex": TRAFFIC_COLORS_HEX["green"],
                "action":    BUCKET_ACTIONS["green"],
            },
            "yellow": {
                "label":     "YELLOW — Proceed",
                "min_value": green_val,
                "max_value": red_val,
                "color_hex": TRAFFIC_COLORS_HEX["yellow"],
                "action":    BUCKET_ACTIONS["yellow"],
            },
            "red": {
                "label":     "RED — Defer",
                "min_value": red_val,
                "color_hex": TRAFFIC_COLORS_HEX["red"],
                "action":    BUCKET_ACTIONS["red"],
            },
        },
        # Grafana native threshold steps format (for direct panel JSON injection)
        "grafana_thresholds": {
            "mode": "absolute",
            "steps": [
                {"color": TRAFFIC_COLORS_GRAFANA["green"],  "value": None},
                {"color": TRAFFIC_COLORS_GRAFANA["yellow"], "value": green_val},
                {"color": TRAFFIC_COLORS_GRAFANA["red"],    "value": red_val},
            ],
        },
    }

    return config


# =============================================================================
# B. HOURLY LOOKUP TABLE  →  season × hour → modal bucket
# =============================================================================

def build_hourly_lookup(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each season × hour, what bucket is most common?
    This is the operator's static reference — no live data needed.
    """
    lookup = (
        df.groupby(["season", "hour"])
        .agg(
            typical_bucket=("bucket", lambda x: x.mode().iloc[0]),
            green_pct=("bucket", lambda x: (x == "green").mean() * 100),
            yellow_pct=("bucket", lambda x: (x == "yellow").mean() * 100),
            red_pct=("bucket", lambda x: (x == "red").mean() * 100),
            avg_moer=("value_mean", "mean"),
        )
        .reset_index()
    )
    lookup["recommendation"] = lookup["typical_bucket"].map(BUCKET_ACTIONS)
    return lookup


# =============================================================================
# C. GRAFANA DASHBOARD JSON
# =============================================================================

def build_grafana_dashboard(thresh_row: pd.Series, region_name: str) -> dict:
    """
    Returns a Grafana dashboard JSON dict ready to import.
    Four panels:
      1. Live traffic light  — Stat panel, current MOER colored by threshold
      2. MOER trend          — Time series with green/red threshold bands
      3. Shift summary       — Table: today's hours by bucket (bar gauge)
      4. Hourly reference    — Static text panel embedding the lookup heatmap
    """
    green_val = float(thresh_row["green_threshold"])
    red_val   = float(thresh_row["red_threshold"])
    region    = thresh_row["region"]

    datasource = {"type": "influxdb", "uid": "${DS_INFLUX}"}

    # Shared threshold definition
    thresholds = {
        "mode": "absolute",
        "steps": [
            {"color": "green",  "value": None},
            {"color": "orange", "value": green_val},
            {"color": "red",    "value": red_val},
        ],
    }

    # InfluxDB flux query for current MOER
    flux_current = (
        f'from(bucket: "watttime")\n'
        f'  |> range(start: -10m)\n'
        f'  |> filter(fn: (r) => r._measurement == "{INFLUX_MEASUREMENT}")\n'
        f'  |> filter(fn: (r) => r._field == "{INFLUX_FIELD_MOER}")\n'
        f'  |> filter(fn: (r) => r.{INFLUX_TAG_REGION} == "{region}")\n'
        f'  |> last()'
    )

    flux_trend = (
        f'from(bucket: "watttime")\n'
        f'  |> range(start: -24h)\n'
        f'  |> filter(fn: (r) => r._measurement == "{INFLUX_MEASUREMENT}")\n'
        f'  |> filter(fn: (r) => r._field == "{INFLUX_FIELD_MOER}")\n'
        f'  |> filter(fn: (r) => r.{INFLUX_TAG_REGION} == "{region}")\n'
        f'  |> aggregateWindow(every: 5m, fn: mean)'
    )

    # Panel: Live traffic light
    panel_light = {
        "id": 1,
        "title": f"Grid Signal — {region_name}",
        "type": "stat",
        "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
        "datasource": datasource,
        "targets": [{"refId": "A", "query": flux_current}],
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "displayName": "MOER (lbs CO₂/MWh)",
                "thresholds": thresholds,
                "color": {"mode": "thresholds"},
                "mappings": [
                    {
                        "type": "range",
                        "options": {
                            "from": 0,
                            "to": green_val,
                            "result": {"text": "🟢 GREEN — Run", "color": "green"},
                        },
                    },
                    {
                        "type": "range",
                        "options": {
                            "from": green_val,
                            "to": red_val,
                            "result": {"text": "🟡 YELLOW — Proceed", "color": "orange"},
                        },
                    },
                    {
                        "type": "range",
                        "options": {
                            "from": red_val,
                            "to": 99999,
                            "result": {"text": "🔴 RED — Defer", "color": "red"},
                        },
                    },
                ],
            }
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": "auto",
            "textMode": "value_and_name",
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "center",
            "text": {"valueSize": 40},
        },
    }

    # Panel: MOER trend with threshold bands
    panel_trend = {
        "id": 2,
        "title": "MOER — Last 24 Hours",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 18, "x": 6, "y": 0},
        "datasource": datasource,
        "targets": [{"refId": "A", "query": flux_trend}],
        "fieldConfig": {
            "defaults": {
                "unit": "short",
                "color": {"mode": "thresholds"},
                "thresholds": thresholds,
                "custom": {
                    "lineWidth": 2,
                    "fillOpacity": 15,
                    "thresholdsStyle": {"mode": "area"},
                },
            }
        },
        "options": {
            "tooltip": {"mode": "single"},
            "legend": {"displayMode": "hidden"},
        },
    }

    # Panel: Threshold reference card (text)
    threshold_text = (
        f"**{region_name} Traffic Light Thresholds**\n\n"
        f"🟢 **GREEN** (≤ {green_val:.0f}) — {BUCKET_ACTIONS['green']}\n\n"
        f"🟡 **YELLOW** ({green_val:.0f} – {red_val:.0f}) — {BUCKET_ACTIONS['yellow']}\n\n"
        f"🔴 **RED** (≥ {red_val:.0f}) — {BUCKET_ACTIONS['red']}\n\n"
        f"*Thresholds = P25/P75 of 2021–2024 MOER distribution.*"
    )

    panel_ref = {
        "id": 3,
        "title": "Operator Reference",
        "type": "text",
        "gridPos": {"h": 5, "w": 12, "x": 0, "y": 8},
        "options": {"mode": "markdown", "content": threshold_text},
    }

    # Panel: Shift summary bar gauge (hours in each bucket today)
    flux_shift = (
        f'from(bucket: "watttime")\n'
        f'  |> range(start: today())\n'
        f'  |> filter(fn: (r) => r._measurement == "{INFLUX_MEASUREMENT}")\n'
        f'  |> filter(fn: (r) => r._field == "{INFLUX_FIELD_MOER}")\n'
        f'  |> filter(fn: (r) => r.{INFLUX_TAG_REGION} == "{region}")\n'
        f'  |> hourSelection(start: {SHIFT_START}h, stop: {SHIFT_END}h)\n'
        f'  |> count()'
    )

    panel_shift = {
        "id": 4,
        "title": f"Today's Shift Summary  (Hours {SHIFT_START}:00–{SHIFT_END}:00)",
        "type": "bargauge",
        "gridPos": {"h": 5, "w": 12, "x": 12, "y": 8},
        "datasource": datasource,
        "targets": [{"refId": "A", "query": flux_shift}],
        "fieldConfig": {
            "defaults": {
                "thresholds": thresholds,
                "color": {"mode": "thresholds"},
                "unit": "short",
            }
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "orientation": "horizontal",
            "displayMode": "lcd",
        },
    }

    dashboard = {
        "title": f"Carbon Traffic Light — {region_name}",
        "uid":   f"carbon-tl-{region.lower().replace('_', '-')}",
        "tags":  ["carbon", "scheduling", "traffic-light"],
        "schemaVersion": 38,
        "version": 1,
        "refresh": "5m",
        "time": {"from": "now-24h", "to": "now"},
        "templating": {
            "list": [
                {
                    "name": "DS_INFLUX",
                    "type": "datasource",
                    "pluginId": "influxdb",
                    "label": "InfluxDB Data Source",
                    "current": {"text": GRAFANA_DATASOURCE_NAME,
                                "value": GRAFANA_DATASOURCE_NAME},
                }
            ]
        },
        "panels": [panel_light, panel_trend, panel_ref, panel_shift],
        "__inputs": [
            {
                "name": "DS_INFLUX",
                "label": "InfluxDB Data Source",
                "type": "datasource",
                "pluginId": "influxdb",
                "pluginName": "InfluxDB",
            }
        ],
    }

    return dashboard


# =============================================================================
# D. OPERATOR REFERENCE CARD (PNG)
# =============================================================================

def plot_hourly_heatmap(lookup: pd.DataFrame, region_name: str,
                        thresh_row: pd.Series, figures_dir: Path,
                        grafana_dir: Path):
    """
    Heatmap: season × hour, colored by green%, with bucket label overlay.
    Saved as both a figure and the operator reference card.
    """
    season_order = ["winter", "spring", "summer", "fall"]

    pivot_green = lookup.pivot(index="season", columns="hour", values="green_pct")
    pivot_green = pivot_green.reindex(season_order)

    pivot_bucket = lookup.pivot(index="season", columns="hour", values="typical_bucket")
    pivot_bucket = pivot_bucket.reindex(season_order)

    fig, ax = plt.subplots(figsize=(16, 4))

    # Color each cell by green%
    sns.heatmap(
        pivot_green, ax=ax,
        cmap="RdYlGn", vmin=0, vmax=100,
        cbar_kws={"label": "Green Hour Probability (%)"},
        linewidths=0.3, linecolor="white",
        annot=False,
    )

    # Overlay bucket letter
    bucket_abbrev = {"green": "G", "yellow": "Y", "red": "R"}
    for row_idx, season in enumerate(season_order):
        for col_idx in range(24):
            if season in pivot_bucket.index and col_idx in pivot_bucket.columns:
                b = pivot_bucket.loc[season, col_idx]
                ax.text(
                    col_idx + 0.5, row_idx + 0.5,
                    bucket_abbrev.get(b, ""),
                    ha="center", va="center",
                    fontsize=7, color="black", fontweight="bold",
                )

    ax.set_title(
        f"{region_name} — Expected Grid Signal by Season and Hour\n"
        f"G = Green (run freely)  |  Y = Yellow (proceed)  |  R = Red (defer)\n"
        f"Green ≤{thresh_row['green_threshold']:.0f}  |  "
        f"Red ≥{thresh_row['red_threshold']:.0f}  (lbs CO₂/MWh)",
        fontsize=11, pad=10,
    )
    ax.set_xlabel("Hour of Day (local)")
    ax.set_ylabel("")
    ax.set_yticklabels([s.capitalize() for s in season_order], rotation=0)

    # Mark shift window
    for x_pos in [SHIFT_START, SHIFT_END + 1]:
        ax.axvline(x=x_pos, color="black", linewidth=1.5, linestyle="--", alpha=0.6)
    ax.text(
        SHIFT_START + 0.2, -0.45, "← shift window →",
        fontsize=8, color="black", alpha=0.7,
    )

    plt.tight_layout()
    heatmap_path = figures_dir / "13_hourly_heatmap.png"
    plt.savefig(heatmap_path, dpi=FIGURE_DPI, bbox_inches="tight")
    plt.close()
    print(f"  Saved: 13_hourly_heatmap.png")
    return heatmap_path


def plot_operator_card(thresh_row: pd.Series, region_name: str,
                       heatmap_path: Path, figures_dir: Path, grafana_dir: Path):
    """
    Printable operator reference card combining:
      - Traffic light with thresholds
      - Recommended actions
      - Hourly heatmap reference
    """
    green_val = thresh_row["green_threshold"]
    red_val   = thresh_row["red_threshold"]

    fig = plt.figure(figsize=(16, 10))
    gs  = GridSpec(2, 4, figure=fig, hspace=0.4, wspace=0.4)

    # --- Traffic lights (left column) ---
    for row, (bucket, color, label, action) in enumerate([
        ("green",  TRAFFIC_COLORS_HEX["green"],  f"GREEN\nMOER ≤ {green_val:.0f}",  BUCKET_ACTIONS["green"]),
        ("yellow", TRAFFIC_COLORS_HEX["yellow"], f"YELLOW\n{green_val:.0f} – {red_val:.0f}", BUCKET_ACTIONS["yellow"]),
        ("red",    TRAFFIC_COLORS_HEX["red"],    f"RED\nMOER ≥ {red_val:.0f}",      BUCKET_ACTIONS["red"]),
    ]):
        ax = fig.add_subplot(gs[row // 2, row % 2] if row < 2 else gs[1, row - 2])
        ax = fig.add_axes([0.01 + row * 0.075, 0.15, 0.07, 0.65])
        circle = plt.Circle((0.5, 0.65), 0.3, color=color, ec="black", lw=2)
        ax.add_patch(circle)
        ax.text(0.5, 0.65, label, ha="center", va="center",
                fontsize=9, fontweight="bold", color="white" if bucket == "red" else "black")
        ax.text(0.5, 0.12, action, ha="center", va="center",
                fontsize=7, wrap=True, color="#333333",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, lw=1.5))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

    # --- Heatmap (right portion) ---
    heatmap_img = plt.imread(str(heatmap_path))
    ax_hm = fig.add_axes([0.27, 0.08, 0.71, 0.85])
    ax_hm.imshow(heatmap_img, aspect="auto")
    ax_hm.axis("off")

    # --- Title bar ---
    fig.text(0.5, 0.97,
             f"Carbon-Aware Scheduling Reference Card — {region_name}",
             ha="center", va="top", fontsize=14, fontweight="bold")
    fig.text(0.5, 0.93,
             f"Post at workstation. Check dashboard for live signal. "
             f"Thresholds calibrated to 2021–2024 MOER distribution (P25/P75).",
             ha="center", va="top", fontsize=9, color="#555555")

    card_path = figures_dir / "13_operator_card.png"
    plt.savefig(card_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved: 13_operator_card.png")

    # Copy to grafana dir too
    import shutil
    shutil.copy(card_path, grafana_dir / "13_operator_card.png")


# =============================================================================
# README
# =============================================================================

def write_readme(thresh_row: pd.Series, region_name: str, grafana_dir: Path):
    readme = f"""
Carbon Traffic Light — Grafana Deployment
==========================================
Region  : {region_name}
Signal  : MOER (lbs CO2/MWh) via WattTime
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Files in this folder
--------------------
thresholds_{thresh_row['region']}.json
    Value mapping config. Green/yellow/red breakpoints for Grafana panels.
    Can be injected directly into a panel's fieldConfig.thresholds block.

hourly_lookup_{thresh_row['region']}.csv
    Season × hour lookup table. Typical bucket (G/Y/R) and green probability
    at each hour. Use as a static reference panel or printed operator card.

13_grafana_dashboard.json
    Complete Grafana dashboard. Import via:
      Dashboards → Import → Upload JSON file
    Then set the DS_INFLUX variable to your InfluxDB data source name.

13_operator_card.png
    Printable reference card. Post at workstation.

Grafana setup
-------------
1. Confirm WattTime MOER values are ingesting into InfluxDB.
   Expected measurement : {INFLUX_MEASUREMENT}
   Field                : {INFLUX_FIELD_MOER}
   Tag                  : {INFLUX_TAG_REGION} = {thresh_row['region']}

2. Import 13_grafana_dashboard.json.

3. Select your InfluxDB data source when prompted.

4. Dashboard auto-refreshes every 5 minutes.

Threshold values
----------------
Green  : MOER <= {thresh_row['green_threshold']:.0f}  (P25 of 2021-2024 distribution)
Yellow : {thresh_row['green_threshold']:.0f} – {thresh_row['red_threshold']:.0f}
Red    : MOER >= {thresh_row['red_threshold']:.0f}  (P75 of 2021-2024 distribution)

Recalibration
-------------
Thresholds are static. Re-run 11_threshold_buckets.py + 13_grafana_operator_deploy.py
annually, or whenever WattTime signals a significant grid mix change for this region.
Wind-dominated grids (SPP, ERCOT) benefit most from annual recalibration.
"""
    (grafana_dir / "README.txt").write_text(readme.strip())
    print("  Saved: README.txt")


# =============================================================================
# MAIN
# =============================================================================

def main():
    run_dir = get_run_dir()
    with open(run_dir / "run_config.json") as f:
        config = json.load(f)
    signal = config["signal"]

    figures_dir = run_dir / "figures"
    outputs_dir = run_dir / "outputs"
    grafana_dir = outputs_dir / "13_grafana"
    grafana_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("GRAFANA OPERATOR DEPLOYMENT")
    print("=" * 70)
    print(f"Run    : {run_dir.name}")
    print(f"Region : {DEPLOY_REGION}")
    print(f"Signal : {signal}")
    print("=" * 70)

    # Load
    thresholds = load_thresholds(run_dir)
    region_row = thresholds[thresholds["region"] == DEPLOY_REGION]
    if len(region_row) == 0:
        print(f"ERROR: Region '{DEPLOY_REGION}' not found in thresholds.")
        print(f"Available: {thresholds['region'].tolist()}")
        sys.exit(1)
    thresh_row  = region_row.iloc[0]
    region_name = thresh_row.get("region_name", DEPLOY_REGION)

    print(f"\nThresholds loaded:")
    print(f"  Green  ≤ {thresh_row['green_threshold']:.0f}")
    print(f"  Yellow   {thresh_row['green_threshold']:.0f} – {thresh_row['red_threshold']:.0f}")
    print(f"  Red    ≥ {thresh_row['red_threshold']:.0f}")

    df = load_hourly(run_dir)
    df_region = df[df["region"] == DEPLOY_REGION].copy()
    df_region = assign_buckets(df_region, thresh_row)

    # A. Threshold config
    print("\n[A] Building threshold config...")
    thresh_config = build_threshold_config(thresh_row)
    thresh_path = grafana_dir / f"thresholds_{DEPLOY_REGION}.json"
    with open(thresh_path, "w") as f:
        json.dump(thresh_config, f, indent=2)
    print(f"  Saved: thresholds_{DEPLOY_REGION}.json")

    # B. Hourly lookup
    print("\n[B] Building hourly lookup table...")
    lookup = build_hourly_lookup(df_region)
    lookup_path = grafana_dir / f"hourly_lookup_{DEPLOY_REGION}.csv"
    lookup.to_csv(lookup_path, index=False)
    print(f"  Saved: hourly_lookup_{DEPLOY_REGION}.csv")

    # C. Grafana dashboard JSON
    print("\n[C] Building Grafana dashboard JSON...")
    dashboard = build_grafana_dashboard(thresh_row, region_name)
    dash_path = grafana_dir / "13_grafana_dashboard.json"
    with open(dash_path, "w") as f:
        json.dump(dashboard, f, indent=2)
    print(f"  Saved: 13_grafana_dashboard.json")

    # D. Operator card
    print("\n[D] Generating operator reference card...")
    heatmap_path = plot_hourly_heatmap(
        lookup, region_name, thresh_row, figures_dir, grafana_dir
    )
    plot_operator_card(thresh_row, region_name, heatmap_path, figures_dir, grafana_dir)

    # README
    write_readme(thresh_row, region_name, grafana_dir)

    print("\n" + "=" * 70)
    print("DEPLOYMENT ARTIFACTS READY")
    print("=" * 70)
    print(f"Grafana folder : {grafana_dir}/")
    print(f"  thresholds_{DEPLOY_REGION}.json  — panel threshold config")
    print(f"  hourly_lookup_{DEPLOY_REGION}.csv — season×hour reference")
    print(f"  13_grafana_dashboard.json         — import into Grafana")
    print(f"  13_operator_card.png              — printable wall card")
    print(f"  README.txt                        — setup instructions")
    print(f"Figures        : {figures_dir}/13_*.png")
    print("=" * 70)
    print("\nNext step: import 13_grafana_dashboard.json into Grafana.")
    print("=" * 70)


if __name__ == "__main__":
    main()
