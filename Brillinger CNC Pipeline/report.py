"""
report.py — turn a run into one self-contained HTML summary.

Figures are embedded as base64 so the report is a single portable file. Tables
render from DataFrames. Sections degrade gracefully: whatever the run produced
gets included, the rest is skipped.

generate_report takes the in-memory objects the entry-point already has, so no
intermediate files are required (though figure PNGs are read from disk to
embed).
"""

from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

_CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     color:#222;max-width:1000px;margin:2rem auto;padding:0 1rem}
h1{font-size:1.7rem;border-bottom:2px solid #2c3e50;padding-bottom:.3rem}
h2{font-size:1.2rem;margin-top:2rem;color:#2c3e50;border-bottom:1px solid #ddd;
   padding-bottom:.2rem}
table{border-collapse:collapse;margin:.6rem 0;font-size:13px}
th,td{border:1px solid #ddd;padding:4px 8px;text-align:right}
th{background:#f4f6f7;text-align:center}
td:first-child,th:first-child{text-align:left}
img{max-width:100%;border:1px solid #eee;margin:.4rem 0}
.note{background:#fef9e7;border-left:4px solid #f39c12;padding:.5rem .8rem;
      margin:.6rem 0;font-size:13px}
.flag{background:#fdedec;border-left:4px solid #c0392b;padding:.5rem .8rem;
      margin:.6rem 0;font-size:13px}
.ok{color:#27ae60}.bad{color:#c0392b}
.meta{color:#777;font-size:12px}
"""


def _b64_img(path: str | Path) -> Optional[str]:
    p = Path(path)
    if not p.exists():
        return None
    data = base64.b64encode(p.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{data}" alt="{html.escape(p.stem)}">'


def _table(df: Optional[pd.DataFrame], caption: str = "", max_rows: int = 50) -> str:
    if df is None or (hasattr(df, "empty") and df.empty):
        return f"<p class='meta'>{html.escape(caption)}: none</p>" if caption else ""
    shown = df.head(max_rows)
    tbl = shown.to_html(index=False, border=0, float_format=lambda x: f"{x:.3f}")
    extra = f"<p class='meta'>showing {max_rows} of {len(df)} rows</p>" if len(df) > max_rows else ""
    cap = f"<p><b>{html.escape(caption)}</b></p>" if caption else ""
    return cap + tbl + extra


def _section(title: str, body: str) -> str:
    return f"<h2>{html.escape(title)}</h2>\n{body}\n"


def generate_report(context: dict, out_path: str | Path,
                    title: str = "Dataset exploration report") -> str:
    """Assemble the HTML report.

    context keys (all optional):
      provenance(dict), manifest(df), per_experiment(df),
      characterization(dict[str,df]), sampling_summary(df),
      feature_correlations(df), feature_table(df),
      anomalies(dict[str,df]), figures(dict[str,path])
    """
    ctx = context
    parts = [f"<!doctype html><html><head><meta charset='utf-8'>",
             f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>",
             f"<h1>{html.escape(title)}</h1>",
             f"<p class='meta'>generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}</p>"]

    # provenance
    prov = ctx.get("provenance")
    if prov:
        rows = "".join(f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
                       for k, v in prov.items())
        parts.append(_section("Run provenance", f"<table>{rows}</table>"))

    # dataset overview
    man = ctx.get("manifest")
    if man is not None and not man.empty:
        n, comp = len(man), int(man["complete"].sum()) if "complete" in man else 0
        overview = (f"<p>{n} experiments, {comp} complete (energy + NC). "
                    f"Materials: {', '.join(map(str, sorted(man['material'].dropna().unique())))}.</p>")
        cols = [c for c in ["experiment", "material", "has_energy", "has_nc",
                            "has_geometry", "energy_mb", "complete"] if c in man.columns]
        parts.append(_section("Dataset overview", overview + _table(man[cols], max_rows=30)))

    # energy characterization
    ch = ctx.get("characterization", {})
    if "by_operation" in ch:
        parts.append(_section("Energy by operation", _table(ch["by_operation"])))
    if "energy_share_by_operation" in ch:
        parts.append(_section("Energy share", _table(ch["energy_share_by_operation"])))
    if "repeatability" in ch:
        parts.append(_section("Repeatability across parts",
                              "<p>Coefficient of variation of part energy within material. "
                              "Low CV means the process is consistent.</p>"
                              + _table(ch["repeatability"])))

    # sampling verdict
    sw = ctx.get("sampling_summary")
    if sw is not None and not sw.empty:
        note = ("<div class='note'>The 1 Hz adequacy answer depends on the meter model. "
                "If block_mean error stays near zero while decimate does not, 1 Hz is fine "
                "only for an integrating meter.</div>")
        parts.append(_section("Sampling-rate sensitivity", note + _table(sw)))

    # figures
    figs = ctx.get("figures", {})
    if figs:
        imgs = []
        for name, path in figs.items():
            tag = _b64_img(path)
            if tag:
                imgs.append(f"<p class='meta'>{html.escape(name)}</p>{tag}")
        if imgs:
            parts.append(_section("Figures", "\n".join(imgs)))

    # feature correlations, with the statistical caveat
    corr = ctx.get("feature_correlations")
    ft = ctx.get("feature_table")
    if corr is not None and not corr.empty:
        n_exp = len(ft) if ft is not None else None
        k = len(corr)
        caveat = (f"<div class='flag'>Exploratory only. With about {n_exp} experiments and "
                  f"{k} features, some strong correlations are expected by chance. Do not "
                  "report these as findings without multiplicity correction or a holdout.</div>")
        parts.append(_section("Feature correlations with energy", caveat + _table(corr)))

    # anomalies
    an = ctx.get("anomalies", {})
    if an:
        blocks = []
        for name, tbl in an.items():
            if isinstance(tbl, pd.DataFrame) and not tbl.empty:
                blocks.append(f"<p><b>{html.escape(name)}</b></p>" + _table(tbl))
        body = "\n".join(blocks) if blocks else "<p class='ok'>No anomalies flagged.</p>"
        parts.append(_section("Anomalies and data quality", body))

    parts.append("</body></html>")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
    return str(out)
