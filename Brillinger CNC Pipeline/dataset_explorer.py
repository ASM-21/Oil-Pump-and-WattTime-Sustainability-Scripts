"""
dataset_explorer.py — explore the whole dataset, not one part.

Turns a dataset directory into something you can interrogate:

  build_manifest        inventory every experiment and its artifacts (the
                        experimental matrix: what is actually in the dataset)
  signal_diagnostics    per-file signal health: sampling regularity, gaps,
                        per-axis activity, spindle duty, transient concentration
                        (the last directly informs the 1 Hz adequacy question)
  corpus_run            batch-process every experiment into one OperationStore,
                        cached to parquet, resilient to bad files, with
                        provenance captured
  characterize_corpus   corpus-level rollups: clean within-dataset material
                        comparison, energy shares, SEC distributions, and
                        repeatability across replicate parts

The corpus runner reuses the validated single-part pipeline; this module adds
the inventory, batching, caching, and characterization around it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import warnings
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import brillinger_pipeline as bp
import material_removal as mr
import operations as ops
from config import DatasetConfig

CODE_VERSION = "0.1.0"
log = logging.getLogger("dataset_explorer")

try:
    import ijson  # noqa: F401
    _HAVE_IJSON = True
except ImportError:
    _HAVE_IJSON = False


# ---------------------------------------------------------------------------
# Config -> pipeline objects
# ---------------------------------------------------------------------------

def channel_map_from_config(cfg: DatasetConfig) -> bp.ChannelMap:
    return bp.ChannelMap(
        power=dict(cfg.channel_power_keys),
        counter_key=cfg.counter_key,
        time_key=cfg.time_key,
        drive_axes=cfg.drive_axes,
    )


# ---------------------------------------------------------------------------
# 1. Manifest
# ---------------------------------------------------------------------------

def _experiment_id(path: Path, mode: str) -> str:
    return path.parent.name if mode == "parent" else path.stem


def build_manifest(dataset_root: str | Path, cfg: DatasetConfig,
                   count_samples: bool = False) -> pd.DataFrame:
    """Inventory the dataset into one row per experiment.

    Globs for energy, NC, and geometry files per cfg, groups them by experiment
    id, and reports which artifacts are present and their sizes. count_samples
    streams each JSON to count samples (slow on large corpora; off by default).
    """
    root = Path(dataset_root)
    if not root.exists():
        raise FileNotFoundError(f"dataset root not found: {root}")

    def _collect(glob_pat):
        out = {}
        for p in root.glob(glob_pat):
            if p.is_file():
                out.setdefault(_experiment_id(p, cfg.experiment_id_from), []).append(p)
        return out

    energy = _collect(cfg.energy_glob)
    nc = _collect(cfg.nc_glob)
    geom = _collect(cfg.geometry_glob)

    exp_ids = sorted(set(energy) | set(nc) | set(geom))
    rows = []
    for eid in exp_ids:
        e = energy.get(eid, [None])[0]
        n = nc.get(eid, [None])[0]
        g = geom.get(eid, [None])[0]
        row = {
            "experiment": eid,
            "material": cfg.material,
            "machine": cfg.machine,
            "has_energy": e is not None,
            "has_nc": n is not None,
            "has_geometry": g is not None,
            "energy_path": str(e) if e else None,
            "nc_path": str(n) if n else None,
            "geometry_path": str(g) if g else None,
            "energy_mb": round(e.stat().st_size / 1e6, 1) if e else np.nan,
            "complete": e is not None and n is not None,
        }
        if count_samples and e is not None:
            row["n_samples"] = _count_samples(e, cfg)
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        log.info("manifest: %d experiments, %d complete (energy+NC)",
                 len(df), int(df["complete"].sum()))
    return df


def _count_samples(json_path: Path, cfg: DatasetConfig) -> float:
    key = next(iter(cfg.channel_power_keys.values()), None)
    if not key:
        return np.nan
    try:
        if _HAVE_IJSON:
            import ijson
            n = 0
            with open(json_path, "rb") as f:
                for _ in ijson.items(f, f"{key}.item"):
                    n += 1
            return n
        with open(json_path) as f:
            data = json.load(f)
        return len(data.get(key, []))
    except Exception as exc:  # noqa: BLE001
        log.warning("sample count failed for %s: %s", json_path.name, exc)
        return np.nan


# ---------------------------------------------------------------------------
# 2. Signal diagnostics
# ---------------------------------------------------------------------------

def signal_diagnostics(power_df: pd.DataFrame, cfg: DatasetConfig,
                       active_w: float = 5.0) -> dict:
    """Per-file signal health and transient concentration.

    transient_top1pct_share is the fraction of total energy carried by the
    top 1% highest-power samples. High concentration means a low-rate meter
    that point-samples will miss energy; near-uniform means 1 Hz is safe even
    when point-sampling. This is the empirical input to the H1 question.
    """
    n = len(power_df)
    dt = cfg.nominal_dt_s
    diag = {"n_samples": n, "nominal_duration_s": n * dt}

    if "time_s" in power_df.columns and n > 1:
        t = power_df["time_s"].to_numpy()
        d = np.diff(t)
        diag["measured_dt_median_s"] = float(np.median(d))
        diag["dt_cv"] = float(np.std(d) / np.mean(d)) if np.mean(d) else np.nan
        gaps = d > 2 * dt
        diag["n_gaps"] = int(gaps.sum())
        diag["max_gap_s"] = float(d.max())
        diag["measured_duration_s"] = float(t[-1] - t[0])

    p = power_df["power_drives_sum"].to_numpy()
    total = float(p.sum())
    diag["mean_power_w"] = float(p.mean()) if n else np.nan
    diag["peak_power_w"] = float(p.max()) if n else np.nan
    diag["peak_to_mean"] = float(p.max() / p.mean()) if n and p.mean() else np.nan
    if n and total:
        k = max(1, int(0.01 * n))
        topk = np.partition(p, -k)[-k:]
        diag["transient_top1pct_share"] = float(topk.sum() / total)

    # per-axis activity
    for axis in cfg.drive_axes:
        col = f"power_{axis}"
        if col in power_df.columns:
            a = power_df[col].to_numpy()
            diag[f"{axis}_active_frac"] = float((np.abs(a) > active_w).mean())
            diag[f"{axis}_mean_w"] = float(a.mean())

    if "power_spindle" in power_df.columns:
        sp = power_df["power_spindle"].to_numpy()
        diag["spindle_active_frac"] = float((sp > active_w).mean())
        idle = sp[sp <= active_w]
        diag["spindle_idle_w"] = float(np.median(idle)) if len(idle) else np.nan

    return diag


# ---------------------------------------------------------------------------
# 3. Cached, resilient corpus runner
# ---------------------------------------------------------------------------

@dataclass
class RunProvenance:
    dataset: str
    dataset_root: str
    code_version: str
    config_hash: str
    timestamp_utc: str
    n_experiments: int
    n_processed: int
    n_failed: int

    def as_dict(self) -> dict:
        return asdict(self)


def _config_hash(cfg: DatasetConfig) -> str:
    relevant = {
        "channel_power_keys": cfg.channel_power_keys,
        "counter_key": cfg.counter_key,
        "drive_axes": list(cfg.drive_axes),
        "nominal_dt_s": cfg.nominal_dt_s,
        "stock_dims_mm": list(cfg.stock_dims_mm),
        "zmap_res_mm": cfg.zmap_res_mm,
        "stock_origin": cfg.stock_origin,
    }
    return hashlib.sha1(json.dumps(relevant, sort_keys=True).encode()).hexdigest()[:12]


def _cache_key(energy_path: str, nc_path: str, cfg_hash: str,
               compute_volume: bool) -> str:
    parts = []
    for p in (energy_path, nc_path):
        try:
            parts.append(f"{p}:{Path(p).stat().st_mtime_ns}")
        except OSError:
            parts.append(str(p))
    parts.append(cfg_hash)
    parts.append("vol" if compute_volume else "novol")
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _save_table(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_parquet(path.with_suffix(".parquet"))
    except Exception:  # noqa: BLE001 - parquet engine may be absent
        with open(path.with_suffix(".pkl"), "wb") as f:
            pickle.dump(df, f)


def _load_table(path: Path) -> Optional[pd.DataFrame]:
    pq, pk = path.with_suffix(".parquet"), path.with_suffix(".pkl")
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:  # noqa: BLE001
            return None
    if pk.exists():
        with open(pk, "rb") as f:
            return pickle.load(f)
    return None


def _process_one(energy_path: str, nc_path: str, cfg: DatasetConfig,
                 cmap: bp.ChannelMap, nc_key: str,
                 compute_volume: bool, tools: Optional[dict]) -> pd.DataFrame:
    """Parse one experiment to a per-operation table (energy + optional volume).
    Returned frame is indexed by operation type."""
    power = bp.load_power_json(energy_path, cmap=cmap)
    nc = bp.parse_mpf(nc_path)
    integ = bp.align_and_integrate(power, nc, nc_key=nc_key,
                                   nominal_dt=cfg.nominal_dt_s)
    table = integ["by_operation"][["energy_j", "time_s", "n_samples"]].copy()

    if compute_volume and tools:
        sim = mr.simulate_removal(nc, tools, stock_dims_mm=cfg.stock_dims_mm,
                                  stock_origin=cfg.stock_origin, res=cfg.zmap_res_mm)
        vol = sim["by_operation"]["volume_mm3"]
        table["volume_mm3"] = vol
    else:
        table["volume_mm3"] = np.nan
    return table


def corpus_run(manifest: pd.DataFrame, cfg: DatasetConfig, *,
               cache_dir: Optional[str | Path] = None,
               nc_key: str = "n_number",
               compute_volume: bool = False,
               tools: Optional[dict] = None) -> dict:
    """Process every complete experiment into one OperationStore.

    Caches each experiment's per-operation table keyed by file mtime + config,
    so re-runs are cheap and a config change invalidates cleanly. Failures are
    logged and skipped, never fatal. Returns store, a per-experiment summary,
    provenance, and the failure list.
    """
    cmap = channel_map_from_config(cfg)
    cfg_hash = _config_hash(cfg)
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    complete = manifest[manifest["complete"]] if "complete" in manifest else manifest
    store = ops.OperationStore()
    per_exp_rows, failures = [], []

    for _, row in complete.iterrows():
        eid, e_path, n_path = row["experiment"], row["energy_path"], row["nc_path"]
        material = row.get("material", cfg.material)
        try:
            table = None
            if cache:
                key = _cache_key(e_path, n_path, cfg_hash, compute_volume)
                table = _load_table(cache / key)
            if table is None:
                table = _process_one(e_path, n_path, cfg, cmap, nc_key,
                                     compute_volume, tools)
                if cache:
                    _save_table(table, cache / _cache_key(e_path, n_path,
                                                          cfg_hash, compute_volume))
            else:
                log.debug("cache hit: %s", eid)

            recs = ops.ops_from_brillinger(
                table, table[["volume_mm3"]] if "volume_mm3" in table else None,
                source=cfg.name, machine=cfg.machine, material=material,
                boundary=cfg.boundary, coolant=cfg.coolant,
                sampling_hz=cfg.sampling_hz, part_id=eid)
            store.extend(recs)

            cut = table.loc["cutting"] if "cutting" in table.index else None
            per_exp_rows.append({
                "experiment": eid, "material": material,
                "n_ops": len(table),
                "energy_j": float(table["energy_j"].sum()),
                "volume_mm3": float(table["volume_mm3"].sum(min_count=1)),
                "cutting_energy_j": float(cut["energy_j"]) if cut is not None else np.nan,
                "cutting_volume_mm3": float(cut["volume_mm3"]) if cut is not None else np.nan,
            })
        except Exception as exc:  # noqa: BLE001
            log.warning("failed on experiment %s: %s", eid, exc)
            failures.append({"experiment": eid, "error": str(exc)})

    per_exp = pd.DataFrame(per_exp_rows)
    if not per_exp.empty and "cutting_volume_mm3" in per_exp:
        with np.errstate(invalid="ignore", divide="ignore"):
            per_exp["cutting_sec"] = per_exp["cutting_energy_j"] / per_exp["cutting_volume_mm3"]

    prov = RunProvenance(
        dataset=cfg.name, dataset_root="", code_version=CODE_VERSION,
        config_hash=cfg_hash,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        n_experiments=len(complete), n_processed=len(per_exp_rows),
        n_failed=len(failures))

    log.info("corpus_run: %d processed, %d failed", prov.n_processed, prov.n_failed)
    return {"store": store, "per_experiment": per_exp,
            "provenance": prov, "failures": failures}


# ---------------------------------------------------------------------------
# 4. Corpus characterization
# ---------------------------------------------------------------------------

def characterize_corpus(store: ops.OperationStore,
                        per_experiment: Optional[pd.DataFrame] = None) -> dict:
    """Corpus-level rollups for exploration.

    The material comparison here is CLEAN: within one dataset the boundary,
    coolant, and machine are constant, so an AlCuMgPb-vs-other SEC ratio is a
    real material effect, not confounded the way the cross-machine comparison
    is. Also returns energy shares, per-operation SEC distribution stats, and
    part-level repeatability.
    """
    out = {}
    df = store.to_frame()
    if df.empty:
        return {"empty": True}

    out["by_operation"] = ops.summarize(store, by="operation_type")
    out["energy_share_by_operation"] = ops.energy_share(store, by="operation_type")

    if df["material"].nunique() > 1:
        try:
            out["material_comparison"] = ops.compare(
                store, dimension="material", basis="marginal",
                operation_types=["cutting"])
        except ValueError:
            pass

    cut = df[(df["operation_type"] == "cutting") & df["sec_marginal"].notna()]
    if not cut.empty:
        g = cut.groupby("material")["sec_marginal"]
        out["cutting_sec_stats"] = pd.DataFrame({
            "n": g.count(), "mean": g.mean(), "median": g.median(),
            "std": g.std(), "cv": g.std() / g.mean(),
        }).reset_index()

    if per_experiment is not None and not per_experiment.empty:
        rep = per_experiment.groupby("material")["energy_j"]
        out["repeatability"] = pd.DataFrame({
            "n_parts": rep.count(), "mean_energy_j": rep.mean(),
            "std_energy_j": rep.std(),
            "cv_energy": rep.std() / rep.mean(),
        }).reset_index()
        out["per_experiment"] = per_experiment

    return out
