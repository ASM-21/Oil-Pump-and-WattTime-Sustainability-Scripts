#!/usr/bin/env python3
"""
generate_report.py
==================

Assemble the outputs of every analysis script into a single self-contained HTML
report (tables inline, plots embedded as base64, so the file stands alone). Run it
after the analyses, or let run_all.py call it. It scans the results root and includes
whatever sections are present, skipping the rest.

Outputs:
  report.html  (into --output, default ./ml/report.html)

Usage
-----
  python generate_report.py --input ./ml --output ./ml/report.html
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# section -> (subdir, title, [(csv, n_rows)], [png])
SECTIONS = [
    ("quality", "Data quality", [("quality_report.csv", 50), ("channel_quality.csv", 50)],
     []),
    ("classify", "Operation classification",
     [("results_algorithms.csv", 10), ("results_per_operation_f1.csv", 50),
      ("results_sensor_ablation.csv", 50)],
     ["per_operation_f1.png", "sensor_ablation.png"]),
    ("energy", "Energy regression",
     [("best_model_per_operation.csv", 50), ("results_pooled.csv", 10)],
     ["energy_r2_by_operation.png"]),
    ("variability", "Run-to-run variability",
     [("variance_explained.csv", 20), ("drift_by_operation.csv", 50)],
     ["energy_cv_by_operation.png", "energy_box_by_operation.png"]),
    ("energy_breakdown", "Energy breakdown",
     [("energy_pareto.csv", 50), ("specific_energy_by_operation.csv", 50)],
     ["energy_by_program.png", "energy_pareto.png"]),
    ("sensor_study", "Sensor study",
     [("mutual_info_operation.csv", 15), ("minimal_set_operation.csv", 15)],
     ["mutual_info.png", "score_vs_sensors.png"]),
    ("scheduling", "Carbon-aware scheduling",
     [("savings_summary.csv", 50)],
     ["carbon_curves.png", "savings_by_strategy.png"]),
    ("timeseries", "Time-series and early prediction",
     [("phase_segmentation.csv", 50), ("early_prediction.csv", 20)],
     ["power_signatures.png", "early_prediction.png", "phase_composition.png"]),
    ("wear", "Tool wear / degradation",
     [("wear_trends.csv", 30), ("rul_estimates.csv", 30)],
     ["wear_trends.png"]),
    ("clustering", "Unsupervised clustering",
     [("cluster_quality.csv", 20), ("submodes.csv", 20)],
     ["pca_projection.png", "cluster_quality.png"]),
    ("carbon", "Carbon footprint",
     [("carbon_pareto.csv", 50), ("material_vs_manufacturing.csv", 5)],
     ["carbon_by_operation.png", "material_vs_manufacturing.png"]),
]

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
margin:0;color:#1a1a1a;background:#f7f7f8}
header{background:#1f2937;color:#fff;padding:24px 32px}
header h1{margin:0 0 4px 0;font-size:22px}
header .sub{color:#cbd5e1;font-size:13px}
nav{padding:12px 32px;background:#fff;border-bottom:1px solid #e5e7eb;font-size:13px}
nav a{color:#2563eb;text-decoration:none;margin-right:14px}
main{max-width:1000px;margin:0 auto;padding:24px 32px}
section{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px 22px;margin:18px 0}
section h2{margin:0 0 12px 0;font-size:18px;border-bottom:2px solid #f3f4f6;padding-bottom:6px}
h3{font-size:13px;color:#374151;margin:16px 0 6px 0;text-transform:uppercase;letter-spacing:.03em}
table{border-collapse:collapse;font-size:12px;margin:4px 0 10px 0;width:100%}
th,td{border:1px solid #e5e7eb;padding:4px 8px;text-align:right}
th{background:#f9fafb;text-align:center}
td:first-child,th:first-child{text-align:left}
img{max-width:100%;height:auto;border:1px solid #eee;border-radius:6px;margin:8px 0}
.missing{color:#9ca3af;font-style:italic;font-size:12px}
"""


def embed_png(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{data}" alt="{path.name}">'


def csv_table(path: Path, n: int) -> str:
    df = pd.read_csv(path)
    html = df.head(n).to_html(index=False, border=0, na_rep="")
    extra = f'<div class="missing">showing {n} of {len(df)} rows</div>' if len(df) > n else ""
    return f"<h3>{path.stem}</h3>{html}{extra}"


def build(root: Path) -> Tuple[str, List[str]]:
    present = []
    body = []
    for key, title, csvs, pngs in SECTIONS:
        sub = root / key
        if not sub.exists():
            continue
        chunks = []
        for name, n in csvs:
            fp = sub / name
            if fp.exists():
                try:
                    chunks.append(csv_table(fp, n))
                except Exception:
                    pass
        for name in pngs:
            fp = sub / name
            if fp.exists():
                chunks.append(embed_png(fp))
        if not chunks:
            continue
        present.append((key, title))
        body.append(f'<section id="{key}"><h2>{title}</h2>{"".join(chunks)}</section>')

    nav = " ".join(f'<a href="#{k}">{t}</a>' for k, t in present)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    head = (f"<header><h1>Operation-level sensor analysis report</h1>"
            f'<div class="sub">Generated {stamp} from {root}/ '
            f"&middot; {len(present)} sections</div></header>")
    html = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>Analysis report</title><style>{CSS}</style></head><body>"
            f"{head}<nav>{nav}</nav><main>{''.join(body)}</main></body></html>")
    return html, [t for _, t in present]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assemble analysis outputs into one HTML report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--input", default="ml", help="Results root containing per-script subfolders.")
    ap.add_argument("--output", default="ml/report.html")
    args = ap.parse_args()

    root = Path(args.input)
    if not root.exists():
        print(f"Results root {root} not found. Run the analyses first.")
        return 1
    html, sections = build(root)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"Report written to {out} with {len(sections)} sections:")
    for s in sections:
        print(f"  - {s}")
    if not sections:
        print("  (no analysis outputs found; run the scripts first)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
