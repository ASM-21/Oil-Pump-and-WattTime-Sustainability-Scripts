"""
config.py — externalized, per-dataset configuration.

Replaces module-level constants scattered across the pipeline. One
DatasetConfig fully describes how to read and characterize a dataset, so
running across machines/datasets is a config change rather than a code edit.

This module is dependency-free (pure data). The runner translates a
DatasetConfig into the concrete objects the pipeline needs (e.g. a ChannelMap),
so config carries no import of the pipeline modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DatasetConfig:
    name: str

    # --- power signal layout ---
    channel_power_keys: dict          # logical axis -> JSON key, e.g. {"x":"POWER|1",...}
    counter_key: str                  # sample->NC link field, e.g. "CYCLE"
    drive_axes: tuple                 # axes summed into the drive-side total
    time_key: Optional[str] = None    # timestamp field if present
    sampling_hz: float = 500.0
    nominal_dt_s: float = 0.002

    # --- material removal ---
    stock_dims_mm: tuple = (125.3, 19.34, 14.52)
    stock_origin: str = "corner"      # corner | center
    zmap_res_mm: float = 0.25

    # --- provenance / comparison metadata ---
    material: str = ""
    machine: str = ""
    boundary: str = "drive_sum"       # drive_sum | machine_input
    coolant: str = "dry"
    process: str = "CNC"

    # --- file discovery globs (relative to dataset root) ---
    energy_glob: str = "**/*.json"
    nc_glob: str = "**/*.mpf"
    geometry_glob: str = "**/*.stl"
    index_glob: str = "**/*.xlsx"
    # how to derive an experiment id from a file: "stem" or "parent"
    experiment_id_from: str = "stem"

    extra: dict = field(default_factory=dict)


# Default for the Brillinger CNC Machining Data Repository. Channel keys and
# counter remain UNVERIFIED against a real file; reconcile via inspect_json
# before a corpus run. Two materials ship in the dataset; set `material` per
# subset or let the manifest attach it.
BRILLINGER = DatasetConfig(
    name="Brillinger",
    channel_power_keys={
        "x": "POWER|1", "y": "POWER|2", "z": "POWER|3", "b": "POWER|4",
        "c": "POWER|5", "spindle": "POWER|6", "magazine": "POWER|7",
    },
    counter_key="CYCLE",
    drive_axes=("x", "y", "z", "b", "c", "spindle", "magazine"),
    time_key=None,
    sampling_hz=500.0,
    nominal_dt_s=0.002,
    stock_dims_mm=(125.3, 19.34, 14.52),
    stock_origin="corner",
    material="AlCuMgPb",
    machine="Spinner U5-630",
    boundary="drive_sum",
    coolant="dry",
    process="CNC",
)


# Template for your IN-MaC data. A single total meter, so boundary is
# machine_input and there is no per-axis breakdown; the channel keys are a
# placeholder since IN-MaC power is ingested per operation, not parsed from
# per-axis JSON. Provided as the second-dataset example.
INMAC = DatasetConfig(
    name="IN-MaC",
    channel_power_keys={},
    counter_key="",
    drive_axes=(),
    sampling_hz=1.0,
    nominal_dt_s=1.0,
    material="Al6061-T6",
    machine="Hurco VMX30Ui",
    boundary="machine_input",
    coolant="flood",
    process="CNC",
)
