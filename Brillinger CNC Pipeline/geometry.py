"""
geometry.py — STL/mesh characterization.

Per-part geometric features: volume, surface area, bounding box, and the
surface-area-to-volume ratio (a proxy for finishing burden, since more surface
per unit volume usually means more finishing passes). Combined with stock size
it also gives removed volume directly, the denominator for aggregate SEC.

Requires trimesh; degrades to an explanatory error if absent. Assumes mm units.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from config import DatasetConfig

log = logging.getLogger("geometry")

try:
    import trimesh
    _HAVE_TRIMESH = True
except ImportError:
    _HAVE_TRIMESH = False


def geometry_features(stl_path: str | Path) -> dict:
    """Geometric features of one mesh. Volume is meaningful only if watertight;
    the flag is reported so you can filter."""
    if not _HAVE_TRIMESH:
        raise ImportError("trimesh not installed; cannot compute geometry.")
    mesh = trimesh.load(str(stl_path))
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.dump(concatenate=True)

    ext = mesh.bounding_box.extents
    vol = float(mesh.volume) if mesh.is_watertight else np.nan
    area = float(mesh.area)
    bbox_vol = float(np.prod(ext))

    return {
        "watertight": bool(mesh.is_watertight),
        "volume_mm3": vol,
        "surface_area_mm2": area,
        "bbox_x_mm": float(ext[0]),
        "bbox_y_mm": float(ext[1]),
        "bbox_z_mm": float(ext[2]),
        "bbox_volume_mm3": bbox_vol,
        "fill_ratio": vol / bbox_vol if (not np.isnan(vol) and bbox_vol) else np.nan,
        "sv_ratio_per_mm": area / vol if (not np.isnan(vol) and vol) else np.nan,
        "n_faces": int(len(mesh.faces)),
        "n_vertices": int(len(mesh.vertices)),
    }


def removed_volume(part_volume_mm3: float, cfg: DatasetConfig) -> float:
    """Stock minus part: the aggregate removed volume for SEC."""
    stock = float(np.prod(cfg.stock_dims_mm))
    return stock - part_volume_mm3


def corpus_geometry(manifest: pd.DataFrame, cfg: Optional[DatasetConfig] = None,
                    max_parts: Optional[int] = None) -> pd.DataFrame:
    """Geometry features for every experiment that has a geometry file. If cfg
    is given, also reports removed volume against the stock."""
    if not _HAVE_TRIMESH:
        log.warning("trimesh unavailable; corpus_geometry returns empty.")
        return pd.DataFrame()
    have = manifest[manifest["has_geometry"]] if "has_geometry" in manifest else manifest
    if max_parts:
        have = have.head(max_parts)
    rows = []
    for _, row in have.iterrows():
        try:
            feat = geometry_features(row["geometry_path"])
            feat["experiment"] = row["experiment"]
            if cfg is not None and not np.isnan(feat["volume_mm3"]):
                feat["removed_volume_mm3"] = removed_volume(feat["volume_mm3"], cfg)
            rows.append(feat)
        except Exception as exc:  # noqa: BLE001
            log.warning("geometry failed on %s: %s", row["experiment"], exc)
    if not rows:
        return pd.DataFrame()
    cols = ["experiment"] + [c for c in rows[0] if c != "experiment"]
    return pd.DataFrame(rows)[cols]
