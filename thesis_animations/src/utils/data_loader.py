"""
Loads grid carbon-intensity (MOER) data per archetype for the scheduling
scene. Looks for data/{archetype}.csv with columns: hour, moer

  hour  : float, 0-24
  moer  : float, marginal operating emissions rate (any consistent unit,
          e.g. lb CO2/MWh or your normalized 0-100 scale)

If no CSV exists for the requested archetype, falls back to a synthetic
duck-curve-shaped trace so the scene still renders, this is a placeholder,
not your actual data. Drop your real WattTime exports into data/ named
after your six archetypes (e.g. data/caiso.csv) to replace it.
"""

import os
import numpy as np

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def _synthetic_moer(hour, seed=0):
    """Placeholder duck-curve trace, deterministic per seed so different
    archetype names still look visually distinct until real data lands."""
    rng_shift = (seed * 2.7) % 5
    morning_peak = 55 * np.exp(-((hour - (8 + rng_shift * 0.3)) ** 2) / 6)
    evening_peak = 70 * np.exp(-((hour - (19 - rng_shift * 0.2)) ** 2) / 8)
    midday_trough = -(30 + rng_shift * 2) * np.exp(-((hour - 13) ** 2) / 12)
    baseline = 45 + rng_shift
    return baseline + morning_peak + evening_peak + midday_trough


def load_moer(archetype: str, resolution: float = 0.1):
    """
    Returns (hours, values, is_synthetic) as numpy arrays plus a flag so
    calling scenes can label the curve "sample data" when appropriate.
    """
    csv_path = os.path.join(DATA_DIR, f"{archetype.lower()}.csv")
    hours = np.arange(0, 24, resolution)

    if os.path.exists(csv_path) and _HAS_PANDAS:
        df = pd.read_csv(csv_path)
        values = np.interp(hours, df["hour"].values, df["moer"].values)
        return hours, values, False

    seed = sum(ord(c) for c in archetype)
    values = np.array([_synthetic_moer(h, seed=seed) for h in hours])
    return hours, values, True
