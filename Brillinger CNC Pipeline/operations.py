"""
operations.py — unified operation model + exploratory analysis spine.

PURPOSE
-------
A source-agnostic substrate for operation-level energy analysis. Any operation,
from this Brillinger pipeline, from your IN-MaC UUID results, from FDM runs,
becomes one normalized record keyed by UUID. Analyses then run over a store of
records regardless of where they came from, so you can ask new questions and
compare across datasets and process types on a common footing.

This module has NO dependency on the Brillinger-specific code. It takes plain
DataFrames/dicts in through adapters and is meant to be dropped into your main
research folder and used on your own data with or without this dataset.

LAYERS
------
  ingestion adapters  (Brillinger pipeline, Z-map, your UUID exports)
        |   ->  OperationRecord
  OperationStore      (holds records from any source, -> tidy frame)
        |
  exploratory engine  (summarize / share / rank / pareto / compare)
                       every comparison auto-reports confounds

OPERATION CONTRACT
------------------
Required to be useful: uuid, source, and at least energy_j (+ volume_mm3 for
SEC, + time_s/baseline_w for marginal energy). Everything else has defaults.
Source-specific signals go in `extra` and are preserved.

EXTENDING
---------
Add a new analysis: write fn(store, **kw) -> DataFrame|dict, then
register("name", fn). Add a new source: write an adapter that yields
OperationRecords. The engine and confound logic need no changes.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field, asdict
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Operation model
# ---------------------------------------------------------------------------

# metadata dimensions that confound an energy comparison, with severity:
#   "blocking_total" -> invalidates a total-basis comparison outright
#   "caveat"         -> comparison stands but the difference is not purely the
#                       dimension under study
CONFOUND_DIMS = {
    "boundary": "blocking_total",
    "process": "caveat",
    "material": "caveat",
    "machine": "caveat",
    "coolant": "caveat",
}

_SEC_LO, _SEC_HI = 0.1, 100.0   # plausible J/mm^3 window for metal cutting


@dataclass
class OperationRecord:
    uuid: str
    source: str
    process: str = "CNC"                 # CNC | FDM | ...
    operation_type: str = "unknown"      # cutting | drilling | rapid | infill ...
    machine: str = ""
    material: str = ""
    boundary: str = ""                   # drive_sum | machine_input | ...
    coolant: str = "unknown"             # dry | flood | mist | na
    sampling_hz: float = float("nan")
    energy_j: float = float("nan")       # on this record's native boundary
    time_s: float = float("nan")
    volume_mm3: float = float("nan")
    baseline_w: float = 0.0
    coolant_w: float = float("nan")
    extra: dict = field(default_factory=dict)

    @property
    def marginal_energy_j(self) -> float:
        if np.isfinite(self.time_s):
            return self.energy_j - self.baseline_w * self.time_s
        return float("nan")

    @property
    def sec_total(self) -> float:
        return self.energy_j / self.volume_mm3 if self.volume_mm3 and self.volume_mm3 > 0 else float("nan")

    @property
    def sec_marginal(self) -> float:
        m = self.marginal_energy_j
        return m / self.volume_mm3 if self.volume_mm3 and self.volume_mm3 > 0 and np.isfinite(m) else float("nan")

    def row(self) -> dict:
        d = asdict(self)
        d.pop("extra")
        d.update({
            "marginal_energy_j": self.marginal_energy_j,
            "sec_total": self.sec_total,
            "sec_marginal": self.sec_marginal,
            "sec_plausible": bool(np.isfinite(self.sec_marginal)
                                  and _SEC_LO <= self.sec_marginal <= _SEC_HI),
            "has_volume": bool(self.volume_mm3 and self.volume_mm3 > 0),
            "marginal_valid": bool(not np.isfinite(self.marginal_energy_j)
                                   or self.marginal_energy_j >= 0),
        })
        return d


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class OperationStore:
    """A collection of OperationRecords from any mix of sources."""

    def __init__(self, records: Optional[Iterable[OperationRecord]] = None):
        self.records: list[OperationRecord] = list(records or [])

    def add(self, rec: OperationRecord) -> "OperationStore":
        self.records.append(rec)
        return self

    def extend(self, recs: Iterable[OperationRecord]) -> "OperationStore":
        self.records.extend(recs)
        return self

    def __len__(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def to_frame(self) -> pd.DataFrame:
        if not self.records:
            return pd.DataFrame()
        return pd.DataFrame([r.row() for r in self.records])

    def filter(self, **equals) -> "OperationStore":
        """Keep records matching all field==value pairs (value may be a set)."""
        def ok(r):
            for k, v in equals.items():
                rv = getattr(r, k)
                if isinstance(v, (set, list, tuple)):
                    if rv not in v:
                        return False
                elif rv != v:
                    return False
            return True
        return OperationStore([r for r in self.records if ok(r)])

    def query(self, expr: str) -> "OperationStore":
        """Filter via a pandas query string on the tidy frame, returning the
        matching records (for arbitrary exploratory slicing)."""
        df = self.to_frame()
        if df.empty:
            return OperationStore()
        keep = set(df.query(expr)["uuid"])
        return OperationStore([r for r in self.records if r.uuid in keep])


# ---------------------------------------------------------------------------
# Weighted SEC helpers
# ---------------------------------------------------------------------------

def _weighted_sec(df: pd.DataFrame, energy_col: str) -> float:
    """Physically correct aggregate SEC: total energy / total volume over the
    rows (volume-weighted), not a mean of per-row SEC."""
    vol = df["volume_mm3"].where(df["volume_mm3"] > 0).sum()
    en = df.loc[df["volume_mm3"] > 0, energy_col].sum()
    return en / vol if vol and vol > 0 else float("nan")


# ---------------------------------------------------------------------------
# Confound detection (generalized from the two-dataset case)
# ---------------------------------------------------------------------------

def detect_confounds(frame_a: pd.DataFrame, frame_b: pd.DataFrame,
                     basis: str) -> list[dict]:
    """Compare the metadata of two operation groups and report every
    confounding dimension on which they differ."""
    out = []
    for dim, severity in CONFOUND_DIMS.items():
        va = set(frame_a[dim].dropna().unique()) if dim in frame_a else set()
        vb = set(frame_b[dim].dropna().unique()) if dim in frame_b else set()
        if va and vb and va != vb:
            out.append({
                "dimension": dim,
                "severity": severity,
                "a": sorted(va),
                "b": sorted(vb),
                "message": _confound_message(dim, sorted(va), sorted(vb),
                                             severity, basis, frame_b),
            })
    return out


def _confound_message(dim, va, vb, severity, basis, frame_b) -> str:
    if dim == "boundary":
        if basis == "total":
            return (f"BOUNDARY: total-basis SEC compares {va} against {vb}. "
                    "Different measurement boundaries; the ratio is not "
                    "interpretable. Use basis='marginal'.")
        return ("BOUNDARY RESIDUAL: marginal energy removes each group's idle "
                "baseline but not load present only during cutting (e.g. a "
                "coolant pump on a total-meter dataset). Not fully isolable.")
    if dim == "coolant":
        cw = frame_b["coolant_w"].dropna() if "coolant_w" in frame_b else pd.Series(dtype=float)
        est = f" (~{cw.iloc[0]:.0f} W on the {vb} side)" if len(cw) else ""
        return (f"COOLANT: {va} vs {vb}. Coolant pump energy is present on one "
                f"side and not the other{est}; not removed by baseline "
                "correction.")
    if dim == "material":
        return (f"MATERIAL: {va} vs {vb}. Specific cutting energy is "
                "material-dependent; this difference is not a machine effect.")
    if dim == "process":
        return (f"PROCESS: {va} vs {vb}. Different process physics; SEC is not "
                "directly comparable, only directionally.")
    if dim == "machine":
        return f"MACHINE: {va} vs {vb}. Drive count, mass, and efficiency differ."
    return f"{dim.upper()}: {va} vs {vb}."


# ---------------------------------------------------------------------------
# Exploratory analyses
# ---------------------------------------------------------------------------

def summarize(store: OperationStore, by) -> pd.DataFrame:
    """Per-group rollup: op count, summed energy/volume/time, and
    volume-weighted total and marginal SEC."""
    df = store.to_frame()
    if df.empty:
        return df
    by = [by] if isinstance(by, str) else list(by)
    rows = []
    for key, g in df.groupby(by):
        rows.append({
            **(dict(zip(by, key if isinstance(key, tuple) else (key,)))),
            "n_ops": len(g),
            "energy_j": g["energy_j"].sum(),
            "volume_mm3": g["volume_mm3"].sum(min_count=1),
            "time_s": g["time_s"].sum(min_count=1),
            "sec_total": _weighted_sec(g, "energy_j"),
            "sec_marginal": _weighted_sec(g, "marginal_energy_j"),
        })
    return pd.DataFrame(rows)


def energy_share(store: OperationStore, by) -> pd.DataFrame:
    """Share of total energy by group (where does the energy go)."""
    df = store.to_frame()
    by = [by] if isinstance(by, str) else list(by)
    s = df.groupby(by)["energy_j"].sum().sort_values(ascending=False)
    out = s.to_frame("energy_j")
    out["share"] = out["energy_j"] / out["energy_j"].sum()
    return out.reset_index()


def rank_operations(store: OperationStore, metric: str = "sec_marginal",
                    n: int = 10, ascending: bool = False) -> pd.DataFrame:
    """Top/bottom operations by a metric (e.g. least efficient cuts, or biggest
    energy consumers with metric='energy_j')."""
    df = store.to_frame()
    cols = ["uuid", "source", "operation_type", "material", "machine",
            metric, "energy_j", "volume_mm3"]
    cols = [c for c in cols if c in df.columns]
    return df.sort_values(metric, ascending=ascending).head(n)[cols].reset_index(drop=True)


def pareto(store: OperationStore, metric: str = "energy_j") -> pd.DataFrame:
    """Cumulative contribution: which operations account for the bulk of a
    metric (80/20 view of energy or volume)."""
    df = store.to_frame().sort_values(metric, ascending=False).copy()
    df = df[df[metric].notna()]
    df["cum"] = df[metric].cumsum()
    df["cum_pct"] = df["cum"] / df[metric].sum()
    return df[["uuid", "source", "operation_type", metric, "cum_pct"]].reset_index(drop=True)


def compare(store: OperationStore, dimension: str, basis: str = "marginal",
            reference=None, operation_types=None) -> dict:
    """Compare SEC across the levels of `dimension` (e.g. 'source', 'material',
    'process'), volume-weighted within each level, with confounds per pair.

    operation_types restricts the comparison (default: cutting only, since SEC
    is only defined where material is removed). reference sets the denominator
    level; default is the first level encountered.
    """
    if basis not in ("marginal", "total"):
        raise ValueError("basis must be marginal|total")
    energy_col = "marginal_energy_j" if basis == "marginal" else "energy_j"

    df = store.to_frame()
    if operation_types is None:
        operation_types = ["cutting"]
    df = df[df["operation_type"].isin(operation_types)]
    if df.empty:
        raise ValueError(f"no operations of types {operation_types} in store.")

    if basis == "marginal":
        bad = df[~df["marginal_valid"]]
        if len(bad):
            warnings.warn(f"dropped {len(bad)} operation(s) with negative "
                          "marginal energy from the comparison (bad baseline or "
                          f"unit error): {list(bad['uuid'])}. Run the "
                          "data_quality probe.")
            df = df[df["marginal_valid"]]

    levels = list(df[dimension].dropna().unique())
    sec = {lvl: _weighted_sec(df[df[dimension] == lvl], energy_col) for lvl in levels}
    ref = reference if reference in sec else levels[0]

    rows, confounds = [], {}
    for lvl in levels:
        ratio = sec[lvl] / sec[ref] if sec[ref] else np.nan
        rows.append({dimension: lvl, "sec": sec[lvl],
                     f"ratio_vs_{ref}": ratio})
        if lvl != ref:
            confounds[(lvl, ref)] = detect_confounds(
                df[df[dimension] == lvl], df[df[dimension] == ref], basis)

    table = pd.DataFrame(rows)
    ratios = table[f"ratio_vs_{ref}"].dropna()
    within_2x = bool(((ratios >= 0.5) & (ratios <= 2.0)).all()) if len(ratios) else None
    blocking = any(c["severity"] == "blocking_total"
                   for pair in confounds.values() for c in pair) and basis == "total"

    return {
        "dimension": dimension, "basis": basis, "reference": ref,
        "table": table, "confounds": confounds,
        "all_within_2x": None if blocking else within_2x,
        "interpretable": not blocking,
    }


def print_comparison(cmp: dict) -> None:
    print(f"compare by '{cmp['dimension']}' | basis: {cmp['basis']} | "
          f"reference: {cmp['reference']}")
    print(cmp["table"].to_string(index=False))
    if not cmp["interpretable"]:
        print("\n** comparison NOT interpretable on this basis (see boundary "
              "confound) **")
    elif cmp["all_within_2x"] is not None:
        print(f"\nall levels within 2x of reference: {cmp['all_within_2x']}")
    print("\nconfounds:")
    if not any(cmp["confounds"].values()):
        print("  none detected (groups share all metadata dimensions)")
    for pair, items in cmp["confounds"].items():
        for c in items:
            print(f"  [{pair[0]} vs {pair[1]}] {c['message']}")


# ---------------------------------------------------------------------------
# Extensible analysis registry
# ---------------------------------------------------------------------------

def data_quality(store: OperationStore) -> pd.DataFrame:
    """Flag operations that would corrupt an analysis: negative marginal energy
    (baseline exceeds total over the interval -> bad baseline or unit error),
    missing volume (no SEC), implausible SEC, or missing time (no marginal).
    Returns only the flagged rows with the reasons."""
    df = store.to_frame()
    if df.empty:
        return df
    issues = []
    for _, r in df.iterrows():
        reasons = []
        if not r["marginal_valid"]:
            reasons.append("negative_marginal_energy")
        if not r["has_volume"]:
            reasons.append("missing_volume")
        if r["has_volume"] and not r["sec_plausible"] and np.isfinite(r["sec_marginal"]):
            reasons.append("implausible_sec")
        if not np.isfinite(r["time_s"]):
            reasons.append("missing_time")
        if reasons:
            issues.append({"uuid": r["uuid"], "source": r["source"],
                           "operation_type": r["operation_type"],
                           "sec_marginal": r["sec_marginal"],
                           "issues": ", ".join(reasons)})
    return pd.DataFrame(issues)


ANALYSES: dict[str, Callable] = {
    "summarize": summarize,
    "energy_share": energy_share,
    "rank": rank_operations,
    "pareto": pareto,
    "compare": compare,
    "data_quality": data_quality,
}


def register(name: str, fn: Callable) -> None:
    ANALYSES[name] = fn


def run(name: str, store: OperationStore, **kw):
    if name not in ANALYSES:
        raise KeyError(f"unknown analysis '{name}'. available: {list(ANALYSES)}")
    return ANALYSES[name](store, **kw)


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def ops_from_brillinger(energy_by_op: pd.DataFrame,
                        volume_by_op: Optional[pd.DataFrame] = None,
                        *, source: str = "Brillinger",
                        machine: str = "Spinner U5-630",
                        material: str = "AlCuMgPb",
                        boundary: str = "drive_sum",
                        coolant: str = "dry",
                        sampling_hz: float = 500.0,
                        baseline_w: float = 0.0,
                        uuid_prefix: str = "brill",
                        part_id: str = "part") -> list[OperationRecord]:
    """Brillinger pipeline outputs -> OperationRecords (one per operation type).

    energy_by_op from bp.align_and_integrate()['by_operation']; volume_by_op
    from mr.simulate_removal()['by_operation']. A synthetic UUID is built per
    operation since the aggregation is per operation type, not per toolpath.
    """
    recs = []
    for op, e in energy_by_op.iterrows():
        vol = float("nan")
        if volume_by_op is not None and op in volume_by_op.index:
            vol = float(volume_by_op.loc[op, "volume_mm3"])
        recs.append(OperationRecord(
            uuid=f"{uuid_prefix}:{part_id}:{op}",
            source=source, process="CNC", operation_type=op,
            machine=machine, material=material, boundary=boundary,
            coolant=coolant, sampling_hz=sampling_hz,
            energy_j=float(e["energy_j"]),
            time_s=float(e["time_s"]) if "time_s" in energy_by_op.columns else float("nan"),
            volume_mm3=vol, baseline_w=baseline_w,
        ))
    return recs


_UUID_PATTS = {
    "uuid": ["uuid", "operation_id", "op_id", "id"],
    "energy_j": ["energy_j", "joule", "energy"],
    "time_s": ["time_s", "duration", "seconds", "time"],
    "volume_mm3": ["volume_mm3", "removed_volume", "volume", "mrr_volume"],
    "operation_type": ["operation_type", "op_type", "operation", "feature"],
    "material": ["material", "stock"],
    "machine": ["machine", "tool_machine"],
    "baseline_w": ["baseline_w", "idle_w", "baseline"],
}


def ops_from_uuid_results(df: pd.DataFrame, *,
                          source: str = "IN-MaC",
                          column_map: Optional[dict] = None,
                          energy_unit: str = "J",
                          defaults: Optional[dict] = None) -> list[OperationRecord]:
    """Ingest YOUR existing per-operation UUID results table.

    Maps your columns to the operation schema. Detection is heuristic; pass
    column_map={'schema_field': 'your_column'} to override, and defaults={...}
    for fields not present as columns (e.g. boundary='machine_input',
    coolant='flood', machine='Hurco VMX30Ui'). Unmapped columns are preserved
    in each record's `extra`. energy_unit in {'J','Wh','kWh'} is converted to J.

    Once you share a header row, the heuristic defaults here can be tightened to
    your exact column names.
    """
    column_map = column_map or {}
    defaults = defaults or {}
    cols = {c.lower(): c for c in df.columns}

    def _detect(field_name):
        if field_name in column_map:
            return column_map[field_name]
        for patt in _UUID_PATTS.get(field_name, []):
            for low, orig in cols.items():
                if patt in low:
                    return orig
        return None

    resolved = {f: _detect(f) for f in _UUID_PATTS}
    e_factor = {"J": 1.0, "Wh": 3600.0, "kWh": 3.6e6}[energy_unit]
    mapped_cols = {v for v in resolved.values() if v}

    recs = []
    for i, row in df.iterrows():
        def _g(f, cast=float, dflt=np.nan):
            col = resolved.get(f)
            if col is None or pd.isna(row[col]):
                return defaults.get(f, dflt)
            return cast(row[col])

        uuid = resolved.get("uuid")
        uuid_val = str(row[uuid]) if uuid and pd.notna(row[uuid]) else f"{source}:{i}"
        extra = {c: row[c] for c in df.columns if c not in mapped_cols}

        recs.append(OperationRecord(
            uuid=uuid_val, source=source,
            process=defaults.get("process", "CNC"),
            operation_type=str(_g("operation_type", str, "unknown")),
            machine=defaults.get("machine", str(_g("machine", str, ""))),
            material=defaults.get("material", str(_g("material", str, ""))),
            boundary=defaults.get("boundary", "machine_input"),
            coolant=defaults.get("coolant", "unknown"),
            sampling_hz=defaults.get("sampling_hz", float("nan")),
            energy_j=_g("energy_j") * e_factor if np.isfinite(_g("energy_j")) else float("nan"),
            time_s=_g("time_s"),
            volume_mm3=_g("volume_mm3"),
            baseline_w=_g("baseline_w", float, 0.0),
            extra=extra,
        ))
    return recs
