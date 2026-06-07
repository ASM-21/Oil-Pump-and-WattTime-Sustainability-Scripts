"""
OpenLCA_gui_tester_V8.py
------------------------
Tkinter GUI for inspecting and updating energy exchange values in OpenLCA.

What changed from V7
--------------------
  Replaced            Monte Carlo now uses OpenLCA's native server-side MC
                      via client.simulate() + simulate_next(). Same algorithm
                      OpenLCA desktop runs - resamples ALL exchanges with
                      uncertainty defined in the database (foreground +
                      background ecoinvent), parameters with uncertainty,
                      and characterization factors with uncertainty.
                      Distribution support: normal, lognormal, triangle,
                      uniform - whatever is defined per exchange.
  Fixed (root cause)  Diagnosed why every prior MC run returned identical
                      samples. olca-ipc 2.x's Result.wait_until_ready()
                      checks `if not state.is_scheduled: return` and
                      returns immediately when called after a previous
                      sample completed but before the server has flipped
                      is_scheduled=True for the new one. Result: every
                      simulate_next was followed by a stale read of the
                      previous sample. The fix is to track ResultState.time
                      and wait for it to advance, not just for is_scheduled
                      to drop.
  New                 Pre-flight check: counts exchanges with uncertainty
                      defined in the foreground process and warns if 0
                      (means Push All wasn't done in Population avg mode,
                      or the database has no uncertainty defined).
  New                 First 5 MC samples are logged in full so the user
                      can see variation happening in real time.
  New                 Connection log shows olca-ipc package version on
                      successful handshake.
  Removed             The V7 "manual" foreground-only MC. If you want
                      that behavior back, restore from V7 - V8 commits
                      to native.

Architecture
------------
  Lines ~1-500    : pure config + backend (no Tk imports in this region)
  Lines ~500-end  : GUI (Tkinter)
  A headless CLI driver can import this module and call backend functions
  directly. The only GUI-touching symbols are inside class App.
"""

import csv
import json
import os
import queue
import random
import shutil
import socket
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from olca_ipc import Client
import olca_schema as o


# ============================================================================
# PATHS + SETTINGS
# ============================================================================
# Files live next to the script for visibility - easier to spot, back up,
# and edit by hand than the previous ~/.openlca_tester location.

def _script_dir() -> Path:
    """Directory containing this script. Falls back to cwd if __file__ missing."""
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd()


APP_DIR       = _script_dir()
PRODUCTS_FILE = APP_DIR / "openlca_products.json"
SETTINGS_FILE = APP_DIR / "openlca_settings.json"
HISTORY_FILE  = APP_DIR / "openlca_history.jsonl"

# One-time migration from the V5 location (~/.openlca_tester).
# Leaves the old files in place; just copies forward if not already migrated.
_LEGACY_DIR = Path.home() / ".openlca_tester"
if _LEGACY_DIR.exists():
    for old_name, new_path in (
        ("products.json", PRODUCTS_FILE),
        ("settings.json", SETTINGS_FILE),
        ("history.jsonl", HISTORY_FILE),
    ):
        old_path = _LEGACY_DIR / old_name
        if old_path.exists() and not new_path.exists():
            try:
                shutil.copy2(old_path, new_path)
                print(f"[migration] copied {old_path} -> {new_path}", file=sys.stderr)
            except Exception as e:
                print(f"[migration] could not copy {old_path}: {e}", file=sys.stderr)


def _atomic_write_text(path: Path, text: str) -> None:
    """
    Write text to path atomically: temp file + os.replace.
    Avoids corruption if the process is killed mid-write.
    On Windows os.replace is atomic on the same volume.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_settings() -> dict:
    """Load persisted settings (host, port, last product). Safe if missing."""
    defaults = {
        "host":           "10.165.42.40",
        "port":           8080,
        "last_product":   "Oil Pump Assembly",
    }
    if not SETTINGS_FILE.exists():
        return defaults
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        defaults.update(data)
        return defaults
    except Exception:
        return defaults


def save_settings(s: dict) -> None:
    _atomic_write_text(SETTINGS_FILE, json.dumps(s, indent=2))


# ============================================================================
# PRODUCT REGISTRY
# ============================================================================

@dataclass
class ExchangeSpec:
    """One electricity input exchange to track in a given product."""
    display_name:      str
    description_match: str   # substring matched (case-insensitive) in ex.description
    default_mean:      float # kWh
    default_std:       float # kWh

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ExchangeSpec":
        return cls(**d)


@dataclass
class Product:
    """A process + its list of electricity exchanges to update."""
    name:              str
    process_id:        str
    product_system_id: str = ""    # optional, only required for LCIA calls
    exchanges:         list = field(default_factory=list)  # list[ExchangeSpec]
    notes:             str = ""

    def to_dict(self) -> dict:
        return {
            "name":              self.name,
            "process_id":        self.process_id,
            "product_system_id": self.product_system_id,
            "exchanges":         [e.to_dict() for e in self.exchanges],
            "notes":             self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Product":
        return cls(
            name              = d["name"],
            process_id        = d["process_id"],
            product_system_id = d.get("product_system_id", ""),
            exchanges         = [ExchangeSpec.from_dict(e) for e in d.get("exchanges", [])],
            notes             = d.get("notes", ""),
        )


# Default ships with the oil pump assembly (from V4 hardcoded values).
# Edit in-app via Manage Products, or directly in ~/.openlca_tester/products.json.
_OIL_PUMP = Product(
    name       = "Oil Pump Assembly",
    process_id = "5cff7493-7b74-4ea2-945b-8eed0441111e",
    product_system_id = "",
    notes      = "Hybrid CNC/AM oil pump. UUID-based 1 Hz power metering.",
    exchanges  = [
        ExchangeSpec("Body P1",     "Body Program 1",     0.343995, 0.088048),
        ExchangeSpec("Body P2",     "Body Program 2",     0.084313, 0.084543),
        ExchangeSpec("Body P3",     "Body Program 3",     0.005297, 0.001486),
        ExchangeSpec("Body P4",     "Body Program 4",     0.065401, 0.061080),
        ExchangeSpec("Lid P1",      "Lid Program 1",      0.127831, 0.003187),
        ExchangeSpec("Lid P2",      "Lid Program 2",      0.173929, 0.013351),
        ExchangeSpec("Drive Gear",  "Drive Gear Electri", 0.421000, 0.080957),
        ExchangeSpec("Drive Shaft", "Drive Shaft Elec",   0.092925, 0.000015),
        ExchangeSpec("Idle Gear",   "Idle Gear Electri",  0.219209, 0.006082),
        ExchangeSpec("Idle Shaft",  "Idle Shaft Elec",    0.058885, 0.004750),
    ],
)


def load_products() -> list[Product]:
    """Load product registry. If file is missing/bad, seed with oil pump default."""
    if not PRODUCTS_FILE.exists():
        save_products([_OIL_PUMP])
        return [_OIL_PUMP]
    try:
        raw = json.loads(PRODUCTS_FILE.read_text())
        return [Product.from_dict(d) for d in raw]
    except Exception as e:
        print(f"[warn] Could not load {PRODUCTS_FILE}: {e}. Using default.", file=sys.stderr)
        return [_OIL_PUMP]


def save_products(products: list[Product]) -> None:
    _atomic_write_text(
        PRODUCTS_FILE,
        json.dumps([p.to_dict() for p in products], indent=2),
    )


# ============================================================================
# COLOR PALETTE (only used by GUI, but kept near config for discoverability)
# ============================================================================

C_OK      = "#2ecc71"
C_ERROR   = "#e74c3c"
C_WARN    = "#f39c12"
C_NEUTRAL = "#95a5a6"
C_BG      = "#1e1e2e"
C_SURFACE = "#2a2a3e"
C_TEXT    = "#cdd6f4"
C_MUTED   = "#6c7086"
C_ACCENT  = "#89b4fa"   # blue  - Exchanges / LCIA
C_ACCENT2 = "#cba6f7"   # mauve - Monte Carlo
C_ACCENT3 = "#f9e2af"   # yellow - spare accent
C_ACCENT4 = "#a6e3a1"   # green  - Contribution


# ============================================================================
# BACKEND - pure IPC helpers, no Tk imports below this section header
# ============================================================================
# Everything from here down to the GUI section is safe to import from a
# headless CLI or test harness. Tk is only imported inside the GUI section.
# ============================================================================

def make_client(host: str, port: int) -> Client:
    """Connect to OpenLCA IPC. Accepts host string + port int."""
    return Client(f"http://{host}:{port}")


def check_server_reachable(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """
    TCP-level reachability probe. Returns (ok, reason).
    The IPC client itself is lazy - it doesn't open a socket on construction -
    so we have to test reachability ourselves before trusting the connection.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, ""
    except socket.timeout:
        return False, f"timeout after {timeout}s"
    except OSError as e:
        return False, str(e)


def fetch_process(client: Client, process_id: str) -> o.Process:
    p = client.get(o.Process, process_id)
    if not p:
        raise ValueError(f"Process not found: {process_id}")
    return p


def _is_electricity_input(ex: o.Exchange) -> bool:
    if not ex.is_input or not ex.flow:
        return False
    return "electricity" in ex.flow.name.lower()


def find_exchange(
    process: o.Process, search: str, warn_cb=None,
) -> o.Exchange | None:
    """
    Find an electricity-input exchange by its description.

    Match strategy (in order):
      1. Exact case-insensitive equality on description -> return immediately.
      2. Substring match. If exactly one substring match, return it.
      3. Multiple substring matches with no exact equal -> log a warning
         via warn_cb and return the SHORTEST description (most specific).

    The shortest-description tiebreaker prevents "Body Program 1" from
    silently matching "Body Program 1, redo" if both ever coexist.
    """
    if not search:
        return None
    s_low = search.lower()

    exact: list[o.Exchange]   = []
    partial: list[o.Exchange] = []
    for ex in process.exchanges:
        if not _is_electricity_input(ex):
            continue
        desc = (ex.description or "").lower()
        if not desc:
            continue
        if desc == s_low:
            exact.append(ex)
        elif s_low in desc:
            partial.append(ex)

    if exact:
        if len(exact) > 1 and warn_cb:
            warn_cb(f"Multiple exact matches for '{search}'; using first.")
        return exact[0]

    if not partial:
        return None

    if len(partial) == 1:
        return partial[0]

    # Multiple substring matches, no exact: pick shortest description.
    partial.sort(key=lambda e: len(e.description or ""))
    if warn_cb:
        descs = [e.description for e in partial]
        warn_cb(
            f"Ambiguous match for '{search}': {len(partial)} candidates "
            f"({descs}). Using shortest: '{partial[0].description}'."
        )
    return partial[0]


def get_current_values(client: Client, process_id: str) -> dict[str, float]:
    """Return {description: amount} for all electricity input exchanges."""
    process = fetch_process(client, process_id)
    out: dict[str, float] = {}
    for ex in process.exchanges:
        if not _is_electricity_input(ex):
            continue
        desc = (ex.description or "").strip()
        if desc:
            out[desc] = ex.amount
    return out


def list_all_exchanges(client: Client, process_id: str) -> list[dict]:
    """
    Return structured list of ALL exchanges for the diagnostics browser.
    Includes uncertainty so the GUI can show std dev.
    """
    process = fetch_process(client, process_id)
    out = []
    for ex in process.exchanges:
        flow_name = ex.flow.name if ex.flow else "(no flow)"
        std = None
        if ex.uncertainty and getattr(ex.uncertainty, "sd", None) is not None:
            std = ex.uncertainty.sd
        out.append({
            "flow":           flow_name,
            "direction":      "input" if ex.is_input else "output",
            "amount":         ex.amount,
            "std":            std,
            "unit":           ex.unit.name if ex.unit else "",
            "description":    ex.description or "",
            "is_electricity": "electricity" in flow_name.lower(),
        })
    return out


def push_one(
    client: Client, process_id: str, product: Product,
    display_name: str, mean: float, std: float | None,
    warn_cb=None,
) -> float:
    """
    Push a single exchange. Returns old amount.
    std=None -> deterministic: clears uncertainty entirely.
    std=number -> population-average: normal distribution with given sd.
    warn_cb is called with a string if the description match is ambiguous.
    """
    spec = next((e for e in product.exchanges if e.display_name == display_name), None)
    search = spec.description_match if spec else display_name
    process = fetch_process(client, process_id)
    ex = find_exchange(process, search, warn_cb=warn_cb)
    if ex is None:
        raise ValueError(f"No exchange for '{display_name}' (searched: '{search}')")
    old = ex.amount
    ex.amount = mean
    if std is None:
        ex.uncertainty = None
    else:
        ex.uncertainty = o.Uncertainty(
            distribution_type = o.UncertaintyType.NORMAL_DISTRIBUTION,
            mean = mean, sd = std,
        )
    client.put(process)
    return old


def push_all(
    client: Client, process_id: str, product: Product,
    values: dict[str, tuple[float, float | None]],
    warn_cb=None,
) -> dict:
    """
    Push all exchanges in a single fetch + put cycle.
    values: {display_name: (mean, std_or_None)}
    std=None on a row -> deterministic for that row.
    warn_cb is called with a string for any ambiguous description matches.
    Returns {'updated': {name: old_val}, 'not_found': [name, ...]}
    """
    process = fetch_process(client, process_id)
    results: dict = {"updated": {}, "not_found": []}
    spec_by_name = {e.display_name: e for e in product.exchanges}

    for name, (mean, std) in values.items():
        spec = spec_by_name.get(name)
        search = spec.description_match if spec else name
        ex = find_exchange(process, search, warn_cb=warn_cb)
        if ex is None:
            results["not_found"].append(name)
            continue
        results["updated"][name] = ex.amount
        ex.amount = mean
        if std is None:
            ex.uncertainty = None
        else:
            ex.uncertainty = o.Uncertainty(
                distribution_type = o.UncertaintyType.NORMAL_DISTRIBUTION,
                mean = mean, sd = std,
            )

    client.put(process)
    return results


def get_descriptors(client: Client, schema_type) -> list[tuple[str, str]]:
    """Return [(id, name), ...] for a schema type. Lightweight first, fallback to get_all."""
    for method in (
        lambda: client.get_descriptors(schema_type),
        lambda: client.get_all(schema_type),
    ):
        try:
            items  = method()
            result = [(i.id, i.name) for i in items
                      if getattr(i, "id", None) and getattr(i, "name", None)]
            if result:
                return sorted(result, key=lambda x: x[1])
        except Exception:
            continue
    return []


def _poll_ready(result, timeout_s: int = 120, interval_s: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if result.get_state().is_ready:
                return True
        except Exception:
            pass
        time.sleep(interval_s)
    return False


def run_lcia_full(
    client: Client, ps_id: str, method_id: str,
) -> list[tuple[str, float, str]]:
    """Full LCIA. Returns [(name, amount, unit), ...] sorted by |amount| desc."""
    setup = o.CalculationSetup(
        target        = o.Ref(ref_type=o.RefType.ProductSystem, id=ps_id),
        impact_method = o.Ref(ref_type=o.RefType.ImpactMethod, id=method_id),
        amount        = 1.0,
    )
    result = client.calculate(setup)
    if not _poll_ready(result):
        result.dispose()
        raise RuntimeError("Timed out waiting for LCIA result.")
    impacts = result.get_total_impacts()
    out = [(i.impact_category.name, i.amount, i.impact_category.ref_unit)
           for i in impacts]
    result.dispose()
    return sorted(out, key=lambda x: abs(x[1]), reverse=True)


def count_uncertainty_in_process(client: Client, process_id: str) -> tuple[int, int]:
    """
    Pre-flight diagnostic: how many exchanges in this process have uncertainty
    defined? Returns (n_with_uncertainty, n_total_exchanges).

    Used to warn the user before MC if their foreground has no uncertainty -
    they probably forgot to Push All in Population avg mode. This does NOT
    inspect background processes (those live in ecoinvent and are checked at
    server side during the simulation).
    """
    process = fetch_process(client, process_id)
    n_total = 0
    n_unc   = 0
    for ex in process.exchanges:
        n_total += 1
        if ex.uncertainty is not None:
            n_unc += 1
    return n_unc, n_total


def run_monte_carlo(
    client: Client,
    ps_id: str, method_id: str,
    n_runs: int = 100,
    progress_cb=None, log_cb=None, cancel_event=None,
    timeout_per_run_s: float = 300.0,
) -> list[tuple[str, float, float, str, list[float]]]:
    """
    Native OpenLCA Monte Carlo via the IPC simulate API.

    This is the SAME algorithm OpenLCA desktop runs when you click
    "Calculate -> Monte Carlo simulation". Per the official manual it
    "considers all uncertainty distributions defined in flows, parameters,
    and characterization factors, with the exception of the one associated
    with the reference product of the system."

    Pattern (olca-ipc 2.x):
        result = client.simulate(setup)
        result.wait_until_ready()        # 1st sample done, READ IT
        for _ in range(n_runs - 1):
            result.simulate_next()       # trigger another sample
            <wait until ResultState.time advances>
            <READ get_total_impacts()>

    The "wait until time advances" step is critical and not what
    Result.wait_until_ready() does. The library's wait_until_ready
    checks `if not state.is_scheduled: return` and returns immediately
    when the prior sample is still showing as ready. That returns BEFORE
    the new simulate_next has been picked up by the server, and the next
    get_total_impacts() reads stale data. We track ResultState.time
    (a timestamp the server bumps per sample) and only proceed once it
    changes. This is why every prior version of this MC returned std=0
    across all categories.

    Returns [(name, mean, std, unit, samples), ...] sorted by |mean| desc.
    """
    setup = o.CalculationSetup(
        target        = o.Ref(ref_type=o.RefType.ProductSystem, id=ps_id),
        impact_method = o.Ref(ref_type=o.RefType.ImpactMethod, id=method_id),
        amount        = 1.0,
    )

    if log_cb:
        log_cb("MC: starting native simulation (client.simulate).")

    result = client.simulate(setup)

    accum: dict[str, list[float]]  = {}
    units: dict[str, str]          = {}

    def _read_sample(run_idx: int) -> tuple[str, float] | None:
        """Read all impacts. Returns (gwp_name, gwp_amount) for logging."""
        gwp = None
        for imp in result.get_total_impacts():
            name = imp.impact_category.name
            accum.setdefault(name, []).append(imp.amount)
            units.setdefault(name, imp.impact_category.ref_unit or "")
            if gwp is None and any(
                k in (name or "").lower()
                for k in ("climate", "gwp", "co2", "global warm")
            ):
                gwp = (name, imp.amount)
        return gwp

    def _wait_for_new_sample(prev_time, run_idx: int) -> int | None:
        """
        Wait until the server has produced a new sample after simulate_next.

        Primary detection: ResultState.time advances from prev_time AND state
        is ready. This is the bulletproof signal because the server bumps
        time per sample.

        Fallback (older servers may not populate time): observe a
        scheduled -> ready state transition. We require to SEE
        is_scheduled=True at least once before accepting is_ready=True;
        otherwise we'd race on the previous sample's ready state.

        Returns the new state.time (may be None on older servers).
        Raises TimeoutError on timeout, RuntimeError on server error.
        """
        # Tiny initial sleep gives the server a chance to flip is_scheduled.
        # Without it we can race on the previous "ready" state.
        time.sleep(0.05)
        deadline = time.monotonic() + timeout_per_run_s
        saw_scheduled = False
        time_field_seen_populated = (prev_time is not None)

        while time.monotonic() < deadline:
            state = result.get_state()
            if state.error:
                raise RuntimeError(f"Server error on run {run_idx + 1}: {state.error}")

            # Primary path: state.time has advanced and we're ready.
            if state.time is not None:
                time_field_seen_populated = True
                if state.is_ready and not state.is_scheduled:
                    if prev_time is None or state.time != prev_time:
                        return state.time

            # Fallback path: only used when time field is unreliable.
            if not time_field_seen_populated:
                if state.is_scheduled:
                    saw_scheduled = True
                elif state.is_ready and saw_scheduled:
                    # Observed a real transition; new sample is ready.
                    return state.time

            time.sleep(0.1)

        raise TimeoutError(
            f"Timed out after {timeout_per_run_s:.0f}s waiting for "
            f"sample {run_idx + 1}."
        )

    completed = 0
    try:
        # First sample: use the library's wait_until_ready - it works fine
        # for the initial computation because there's no prior ready-state
        # to race with.
        first_state = result.wait_until_ready()
        if first_state.error:
            raise RuntimeError(f"Initial simulation failed: {first_state.error}")
        prev_time = first_state.time
        gwp = _read_sample(0)
        completed = 1
        if progress_cb:
            progress_cb(1, n_runs)
        if log_cb:
            if gwp:
                log_cb(f"  MC run 1: {gwp[0][:40]} = {gwp[1]:.6g}  "
                       f"(state.time={prev_time})")
            else:
                log_cb(f"  MC run 1: read {len(accum)} impact categories.")

        # Remaining samples
        for i in range(1, n_runs):
            if cancel_event is not None and cancel_event.is_set():
                if log_cb:
                    log_cb(f"MC cancelled after {completed}/{n_runs} runs.")
                break

            result.simulate_next()
            prev_time = _wait_for_new_sample(prev_time, i)
            gwp = _read_sample(i)
            completed = i + 1
            if progress_cb:
                progress_cb(completed, n_runs)

            # Log first 5 in full + every 25th after, so the user can SEE
            # values changing iteration to iteration.
            if log_cb and gwp and (i < 5 or i % 25 == 0):
                log_cb(f"  MC run {i+1}: {gwp[0][:40]} = {gwp[1]:.6g}  "
                       f"(state.time={prev_time})")

    finally:
        try:
            result.dispose()
        except Exception as e:
            if log_cb:
                log_cb(f"WARNING dispose failed: {e}")

    out = []
    for name, vals in accum.items():
        mean = statistics.fmean(vals) if vals else 0.0
        std  = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        out.append((name, mean, std, units[name], vals))
    out.sort(key=lambda x: abs(x[1]), reverse=True)

    # Sanity check: if EVERY category came back std=0, something is wrong.
    # Most likely: no uncertainty defined anywhere in the system, OR the
    # state.time field wasn't updating and we're still reading stale data.
    if log_cb and out and all(s == 0.0 for _, _, s, _, _ in out):
        log_cb("WARNING: every impact category returned std=0. Either no "
               "uncertainty is defined in the system, or the server state "
               "isn't reporting new samples. Check the foreground process "
               "in Diagnostics (Show std dev) and confirm Push All was run "
               "in Population avg mode.")

    return out


# ============================================================================
# DATA I/O (CSV + history log)
# ============================================================================

def export_exchanges_csv(
    path: str,
    values: dict[str, tuple[float, float | None]],
    part_ids: dict[str, str] | None = None,
) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["display_name", "mean_kWh", "std_kWh", "part_id"])
        for name, (m, s) in values.items():
            pid = (part_ids or {}).get(name, "")
            w.writerow([name, m, "" if s is None else s, pid])


def import_exchanges_csv(path: str) -> tuple[dict[str, tuple[float, float | None]], dict[str, str]]:
    values: dict[str, tuple[float, float | None]] = {}
    part_ids: dict[str, str] = {}
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row.get("display_name") or row.get("name")
            if not name:
                continue
            mean = float(row.get("mean_kWh") or row.get("mean") or 0.0)
            std_raw = row.get("std_kWh") or row.get("std") or ""
            std = None if std_raw == "" else float(std_raw)
            values[name] = (mean, std)
            pid = (row.get("part_id") or "").strip()
            if pid:
                part_ids[name] = pid
    return values, part_ids


def export_impacts_csv(path: str, impacts: list[tuple[str, float, str]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "amount", "unit"])
        for row in impacts:
            w.writerow(row)


def append_history(event: dict) -> None:
    event["ts"] = datetime.now().isoformat(timespec="seconds")
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


# ============================================================================
# END OF BACKEND SECTION - Tk imports start below
# ============================================================================


import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Matplotlib (embedded)
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ============================================================================
# GUI UTILITIES
# ============================================================================

def _scrollable(parent: tk.Widget) -> tk.Frame:
    """
    Attach a vertical scrollbar and return an inner Frame for content.
    The mouse wheel only scrolls THIS canvas while the cursor is over it -
    no global bind_all collision between tabs (V5 had every scrollable
    region fighting for a single global wheel handler).
    """
    canvas = tk.Canvas(parent, bg=C_BG, highlightthickness=0)
    sb     = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner  = tk.Frame(canvas, bg=C_BG)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(win_id, width=e.width))
    inner.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    # Windows-only mouse wheel: route to THIS canvas only while hovered.
    def _on_wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def _bind_wheel(_e):
        canvas.bind_all("<MouseWheel>", _on_wheel)
    def _unbind_wheel(_e):
        canvas.unbind_all("<MouseWheel>")

    canvas.bind("<Enter>", _bind_wheel)
    canvas.bind("<Leave>", _unbind_wheel)
    inner.bind("<Enter>",  _bind_wheel)
    inner.bind("<Leave>",  _unbind_wheel)

    return inner


def _lbl(parent, text, width=None, anchor="w",
         fg=C_TEXT, font=("Helvetica", 10), **kw):
    return tk.Label(parent, text=text, width=width, anchor=anchor,
                    bg=C_BG, fg=fg, font=font, **kw)


def _header_row(parent, headers: list, widths: list):
    for col, (h, w) in enumerate(zip(headers, widths)):
        _lbl(parent, h, width=w, fg=C_MUTED,
             font=("Helvetica", 10, "bold")
             ).grid(row=0, column=col, padx=5, pady=(0, 6), sticky="w")


def _btn(parent, text, command, color=C_SURFACE, fg=C_TEXT,
         bold=False, pad_x=12, pad_y=4):
    f = ("Helvetica", 10, "bold") if bold else ("Helvetica", 10)
    return tk.Button(parent, text=text, bg=color, fg=fg, relief="flat",
                     font=f, padx=pad_x, pady=pad_y, command=command,
                     activebackground=C_SURFACE, activeforeground=C_TEXT)


def _mpl_figure(parent, figsize=(6, 3.2)) -> tuple[Figure, FigureCanvasTkAgg]:
    """Create a dark-themed matplotlib figure embedded in a Tk parent."""
    fig = Figure(figsize=figsize, dpi=100, facecolor=C_BG)
    ax = fig.add_subplot(111)
    _restyle_axes_dark(ax)
    canvas = FigureCanvasTkAgg(fig, master=parent)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    return fig, canvas


def _restyle_axes_dark(ax) -> None:
    """
    Reapply dark-theme colors to an axes.
    Must be called after ax.clear() - matplotlib resets text colors on clear.
    This was the bug in V4's MC / Contribution / Scenario plots.
    """
    ax.set_facecolor(C_SURFACE)
    for spine in ax.spines.values():
        spine.set_color(C_MUTED)
    ax.tick_params(colors=C_TEXT, labelsize=8)
    ax.xaxis.label.set_color(C_TEXT)
    ax.yaxis.label.set_color(C_TEXT)
    ax.title.set_color(C_TEXT)


def _save_fig_png(fig: Figure, default_name: str) -> None:
    """Prompt for a path and save the figure as PNG."""
    path = filedialog.asksaveasfilename(
        title="Export plot as PNG",
        defaultextension=".png",
        initialfile=default_name,
        filetypes=[("PNG images", "*.png")],
    )
    if not path:
        return
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")


# ============================================================================
# MAIN APP
# ============================================================================

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("OpenLCA Energy Updater")
        self.configure(bg=C_BG)
        self.resizable(True, True)
        self.minsize(1080, 720)

        # --- Persistent state --------------------------------------------
        self.settings = load_settings()
        self.products: list[Product] = load_products()
        self.current_product: Product = self._pick_initial_product()

        # --- Runtime state -----------------------------------------------
        self.client: Client | None = None
        self.row_widgets: list[dict] = []    # rebuilt on product change
        self._row_gen: int = 0               # bumps on every row rebuild;
                                             # background threads check this
                                             # to avoid writing to destroyed
                                             # widgets after a product switch.
        self._ps_map:     dict[str, str] = {}
        self._method_map: dict[str, str] = {}
        self._ps_var     = tk.StringVar()
        self._method_var = tk.StringVar()
        self._product_var = tk.StringVar(value=self.current_product.name)

        # Push mode: "population" (mean+std, normal distribution)
        #            "specific"   (deterministic, optional part_id tag)
        self._push_mode = tk.StringVar(value="population")

        # Last LCIA results for delta display
        self._lcia_prev: dict[str, float] = {}
        self._lcia_baseline_ts: str | None = None  # human-readable "set when"

        # Monte Carlo cancel signal - threading.Event
        self._mc_cancel = threading.Event()

        # Host/port editable fields
        self._host_var = tk.StringVar(value=self.settings["host"])
        self._port_var = tk.StringVar(value=str(self.settings["port"]))

        # UI -> main thread marshalling
        self._ui_queue: "queue.Queue[callable]" = queue.Queue()

        self._build_ui()
        self.after(50, self._drain_ui_queue)
        self._connect_and_refresh()

    def _pick_initial_product(self) -> Product:
        want = self.settings.get("last_product")
        for p in self.products:
            if p.name == want:
                return p
        return self.products[0]

    # ------------------------------------------------------------------ #
    # UI CONSTRUCTION                                                    #
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        self._build_header()
        self._build_config_bar()
        self._build_config_help()
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=8, pady=(4, 0))
        self._build_notebook()

    def _build_config_help(self):
        """Tiny explainer line - clears up Product vs Product System."""
        f = tk.Frame(self, bg=C_BG)
        f.pack(fill="x", padx=16, pady=(0, 2))
        tk.Label(
            f,
            text=("Product = local app entry (process UUID + tracked exchanges).   "
                  "Product System = OpenLCA's calculation graph that LCIA runs against. "
                  "One Product can have multiple Product Systems in OpenLCA; "
                  "pick the one you want to score."),
            bg=C_BG, fg=C_MUTED, font=("Helvetica", 8, "italic"),
            anchor="w", justify="left", wraplength=1400,
        ).pack(side="left", anchor="w")

    def _build_header(self):
        f = tk.Frame(self, bg=C_BG, pady=8)
        f.pack(fill="x", padx=16)
        tk.Label(f, text="OpenLCA  Energy Updater",
                 font=("Helvetica", 15, "bold"),
                 bg=C_BG, fg=C_ACCENT).pack(side="left")
        self._status_lbl = tk.Label(f, text="Connecting...",
                                    font=("Helvetica", 9),
                                    bg=C_BG, fg=C_MUTED)
        self._status_lbl.pack(side="right")

    def _build_config_bar(self):
        f = tk.Frame(self, bg=C_BG, pady=4)
        f.pack(fill="x", padx=16)

        # Product selector + manage
        _lbl(f, "Product:", fg=C_MUTED, font=("Helvetica", 9)).pack(side="left")
        self._product_combo = ttk.Combobox(
            f, textvariable=self._product_var,
            width=22, state="readonly",
            values=[p.name for p in self.products],
        )
        self._product_combo.pack(side="left", padx=(4, 6))
        self._product_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_product_change())
        _btn(f, "Manage...", self._open_products_dialog, pad_x=6, pad_y=2).pack(side="left", padx=(0, 14))

        _lbl(f, "Product System:", fg=C_MUTED, font=("Helvetica", 9)).pack(side="left")
        self._ps_combo = ttk.Combobox(f, textvariable=self._ps_var,
                                      width=26, state="readonly")
        self._ps_combo.pack(side="left", padx=(4, 10))

        _lbl(f, "LCIA Method:", fg=C_MUTED, font=("Helvetica", 9)).pack(side="left")
        self._method_combo = ttk.Combobox(f, textvariable=self._method_var,
                                          width=26, state="readonly")
        self._method_combo.pack(side="left", padx=(4, 10))

        # Host / port editable
        _lbl(f, "Host:", fg=C_MUTED, font=("Helvetica", 9)).pack(side="left", padx=(8, 0))
        tk.Entry(f, textvariable=self._host_var, width=14,
                 bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Courier", 9)
                 ).pack(side="left", padx=(4, 4))
        _lbl(f, ":", fg=C_MUTED, font=("Helvetica", 9)).pack(side="left")
        tk.Entry(f, textvariable=self._port_var, width=6,
                 bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                 relief="flat", font=("Courier", 9)
                 ).pack(side="left", padx=(4, 8))

        _btn(f, "Refresh Lists", self._load_descriptors_in_thread,
             pad_x=6, pad_y=2).pack(side="left")
        _btn(f, "Reconnect", self._connect_and_refresh,
             pad_x=6, pad_y=2).pack(side="left", padx=(6, 0))

    def _build_notebook(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("TNotebook",     background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=C_SURFACE, foreground=C_MUTED,
                        padding=[14, 6], font=("Helvetica", 10))
        style.map("TNotebook.Tab",
                  background=[("selected", C_BG)],
                  foreground=[("selected", C_ACCENT)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._tab_exch  = tk.Frame(nb, bg=C_BG); nb.add(self._tab_exch,  text="Exchanges")
        self._tab_lcia  = tk.Frame(nb, bg=C_BG); nb.add(self._tab_lcia,  text="LCIA Results")
        self._tab_mc    = tk.Frame(nb, bg=C_BG); nb.add(self._tab_mc,    text="Monte Carlo")
        self._tab_diag  = tk.Frame(nb, bg=C_BG); nb.add(self._tab_diag,  text="Diagnostics")

        self._build_exchanges_tab()
        self._build_lcia_tab()
        self._build_mc_tab()
        self._build_diagnostics_tab()

    # ==================================================================
    # TAB 1: EXCHANGES (push mode selector + Part ID column)
    # ==================================================================

    def _build_exchanges_tab(self):
        tab = self._tab_exch

        # ---- Mode selector strip ----------------------------------------
        mode_frame = tk.Frame(tab, bg=C_BG, pady=6)
        mode_frame.pack(fill="x", padx=16)

        _lbl(mode_frame, "Push mode:", fg=C_MUTED,
             font=("Helvetica", 9, "bold")).pack(side="left")
        tk.Radiobutton(
            mode_frame, text="Population avg (mean + std, uncertainty pushed)",
            variable=self._push_mode, value="population",
            bg=C_BG, fg=C_TEXT, selectcolor=C_SURFACE,
            activebackground=C_BG, activeforeground=C_ACCENT,
            font=("Helvetica", 9),
            command=self._on_mode_change,
        ).pack(side="left", padx=(8, 4))
        tk.Radiobutton(
            mode_frame, text="Specific part (deterministic, uncertainty cleared)",
            variable=self._push_mode, value="specific",
            bg=C_BG, fg=C_TEXT, selectcolor=C_SURFACE,
            activebackground=C_BG, activeforeground=C_ACCENT4,
            font=("Helvetica", 9),
            command=self._on_mode_change,
        ).pack(side="left", padx=(8, 4))

        # ---- Product context ---------------------------------------------
        ctx = tk.Frame(tab, bg=C_BG)
        ctx.pack(fill="x", padx=16)
        self._product_ctx_lbl = tk.Label(
            ctx, text="", bg=C_BG, fg=C_MUTED, font=("Helvetica", 9, "italic")
        )
        self._product_ctx_lbl.pack(side="left")

        # ---- Scrollable rows ---------------------------------------------
        outer = tk.Frame(tab, bg=C_BG)
        outer.pack(fill="both", expand=True, padx=8, pady=8)
        self._exch_inner = _scrollable(outer)
        self._build_exchange_rows()

        # ---- Bottom controls --------------------------------------------
        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=8, pady=(4, 0))
        bot = tk.Frame(tab, bg=C_BG, pady=8)
        bot.pack(fill="x", padx=16)

        for text, cmd in (
            ("Refresh from Server",  self._refresh_in_thread),
            ("Reset to Defaults",    self._reset_to_defaults),
            ("Import CSV",           self._import_csv),
            ("Export CSV",           self._export_exchanges_csv),
        ):
            _btn(bot, text, cmd).pack(side="left", padx=(0, 8))

        _btn(bot, "Push All", self._push_all_in_thread,
             color=C_ACCENT, fg=C_BG, bold=True, pad_x=16).pack(side="left")

        self._push_all_lbl = tk.Label(bot, text="",
                                      font=("Helvetica", 10),
                                      bg=C_BG, fg=C_OK)
        self._push_all_lbl.pack(side="right")

    def _build_exchange_rows(self):
        """(Re)build the exchange rows for self.current_product."""
        # Clear existing
        for w in self._exch_inner.winfo_children():
            w.destroy()
        self.row_widgets = []
        self._row_gen += 1   # invalidate any in-flight thread updates

        # Update header - Part ID column only visible in 'specific' mode
        specific_mode = (self._push_mode.get() == "specific")
        if specific_mode:
            headers = ["Component", "Current (kWh)", "New Value (kWh)",
                       "Std Dev (kWh)", "Part ID", "Status", ""]
            widths  = [14, 14, 14, 13, 14, 18, 8]
        else:
            headers = ["Component", "Current (kWh)", "New Value (kWh)",
                       "Std Dev (kWh)", "Status", ""]
            widths  = [14, 14, 14, 13, 20, 8]
        _header_row(self._exch_inner, headers, widths)

        for ri, spec in enumerate(self.current_product.exchanges, start=1):
            row: dict = {"desc": spec.display_name, "spec": spec}

            _lbl(self._exch_inner, spec.display_name, width=14).grid(
                row=ri, column=0, padx=5, pady=3, sticky="w")

            cur_var = tk.StringVar(value="--")
            tk.Label(self._exch_inner, textvariable=cur_var, width=14, anchor="w",
                     bg=C_BG, fg=C_MUTED, font=("Courier", 10)
                     ).grid(row=ri, column=1, padx=5, pady=3, sticky="w")

            new_var = tk.StringVar(value=f"{spec.default_mean:.6f}")
            tk.Entry(self._exch_inner, textvariable=new_var, width=14,
                     bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                     relief="flat", font=("Courier", 10)
                     ).grid(row=ri, column=2, padx=5, pady=3, sticky="w")

            std_var = tk.StringVar(value=f"{spec.default_std:.6f}")
            std_entry = tk.Entry(self._exch_inner, textvariable=std_var, width=13,
                                 bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                                 relief="flat", font=("Courier", 10))
            std_entry.grid(row=ri, column=3, padx=5, pady=3, sticky="w")
            if specific_mode:
                std_entry.configure(state="disabled", fg=C_MUTED)

            # Part ID column (specific mode only)
            col = 4
            part_var = tk.StringVar(value="")
            if specific_mode:
                tk.Entry(self._exch_inner, textvariable=part_var, width=14,
                         bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                         relief="flat", font=("Courier", 10)
                         ).grid(row=ri, column=col, padx=5, pady=3, sticky="w")
                col += 1

            sv = tk.StringVar(value="")
            sl = tk.Label(self._exch_inner, textvariable=sv,
                          width=18 if specific_mode else 20, anchor="w",
                          bg=C_BG, fg=C_NEUTRAL, font=("Helvetica", 9))
            sl.grid(row=ri, column=col, padx=5, pady=3, sticky="w")
            col += 1

            _btn(self._exch_inner, "Push",
                 command=lambda d=spec.display_name,
                                nv=new_var, sv2=std_var, pv=part_var,
                                sl2=sl, svv=sv:
                    self._push_row(d, nv, sv2, pv, sl2, svv),
                 color=C_ACCENT, fg=C_BG, bold=True, pad_x=8, pad_y=2
                 ).grid(row=ri, column=col, padx=5, pady=3)

            row.update(current_var=cur_var, new_var=new_var, std_var=std_var,
                       part_var=part_var, status_var=sv, status_lbl=sl,
                       std_entry=std_entry)
            self.row_widgets.append(row)

        self._update_product_ctx_label()

    def _update_product_ctx_label(self):
        p = self.current_product
        txt = f"process_id: {p.process_id}"
        if p.product_system_id:
            txt += f"  |  product_system_id: {p.product_system_id}"
        self._product_ctx_lbl.config(text=txt)

    def _on_mode_change(self):
        """Rebuild rows to show/hide Part ID + enable/disable std dev."""
        # Preserve current entered values where possible
        saved = {
            r["desc"]: {
                "new":  r["new_var"].get(),
                "std":  r["std_var"].get(),
                "part": r["part_var"].get(),
            } for r in self.row_widgets
        }
        self._build_exchange_rows()
        for r in self.row_widgets:
            if r["desc"] in saved:
                r["new_var"].set(saved[r["desc"]]["new"])
                r["std_var"].set(saved[r["desc"]]["std"])
                r["part_var"].set(saved[r["desc"]]["part"])
        mode = self._push_mode.get()
        self._log(f"Push mode -> {mode}")

    def _reset_to_defaults(self):
        for r, spec in zip(self.row_widgets, self.current_product.exchanges):
            r["new_var"].set(f"{spec.default_mean:.6f}")
            r["std_var"].set(f"{spec.default_std:.6f}")
            r["part_var"].set("")
            r["status_var"].set("reset")
            r["status_lbl"].config(fg=C_MUTED)
        self._log(f"Exchange rows reset to defaults for '{self.current_product.name}'.")

    # ==================================================================
    # TAB 3: LCIA RESULTS (with delta from previous run)
    # ==================================================================

    def _build_lcia_tab(self):
        tab = self._tab_lcia

        top = tk.Frame(tab, bg=C_BG)
        top.pack(fill="x", padx=16, pady=8)
        _btn(top, "Run LCIA", self._lcia_in_thread,
             color=C_ACCENT, fg=C_BG, bold=True, pad_x=16).pack(side="left")
        _btn(top, "Export CSV", self._export_impacts_csv).pack(side="left", padx=(8, 0))
        _btn(top, "Clear Delta Baseline", self._clear_lcia_prev).pack(side="left", padx=(8, 0))

        self._lcia_status = tk.Label(top, text="",
                                     font=("Helvetica", 10),
                                     bg=C_BG, fg=C_MUTED)
        self._lcia_status.pack(side="left", padx=12)

        # Baseline / verification status line.
        baseline_row = tk.Frame(tab, bg=C_BG)
        baseline_row.pack(fill="x", padx=16, pady=(0, 4))
        self._lcia_baseline_lbl = tk.Label(
            baseline_row,
            text="No LCIA run yet.  Run once to see results, run again to see how they changed.",
            bg=C_BG, fg=C_MUTED, font=("Helvetica", 9, "italic"),
            anchor="w", justify="left",
        )
        self._lcia_baseline_lbl.pack(side="left", anchor="w")

        # Verification hint - one line, always visible.
        verify_row = tk.Frame(tab, bg=C_BG)
        verify_row.pack(fill="x", padx=16, pady=(0, 4))
        tk.Label(
            verify_row,
            text=("Values come straight from result.get_total_impacts() for the "
                  "selected Product System + LCIA Method. Cross-check by running "
                  "the same setup in the OpenLCA desktop app."),
            bg=C_BG, fg=C_MUTED, font=("Helvetica", 8, "italic"),
            anchor="w", justify="left", wraplength=1400,
        ).pack(side="left", anchor="w")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=8)

        # Treeview: tree column = category name (resizable), 3 data columns.
        body = tk.Frame(tab, bg=C_BG)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        self._lcia_tree = ttk.Treeview(
            body,
            columns=("amount", "unit", "delta"),
            show="tree headings", height=20,
        )
        self._lcia_tree.heading("#0",     text="Impact Category")
        self._lcia_tree.heading("amount", text="Amount")
        self._lcia_tree.heading("unit",   text="Unit")
        self._lcia_tree.heading("delta",  text="Δ vs prev")
        self._lcia_tree.column("#0",     width=440, anchor="w", stretch=True)
        self._lcia_tree.column("amount", width=140, anchor="e", stretch=False)
        self._lcia_tree.column("unit",   width=140, anchor="w", stretch=False)
        self._lcia_tree.column("delta",  width=110, anchor="e", stretch=False)

        sb = ttk.Scrollbar(body, orient="vertical", command=self._lcia_tree.yview)
        self._lcia_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._lcia_tree.pack(side="left", fill="both", expand=True)

        # Tag colors for GWP highlight + delta direction
        self._lcia_tree.tag_configure("gwp",       foreground=C_ACCENT)
        self._lcia_tree.tag_configure("delta_dn",  foreground=C_OK)
        self._lcia_tree.tag_configure("delta_up",  foreground=C_ERROR)

        self._lcia_last: list[tuple[str, float, str]] = []

    def _clear_lcia_prev(self):
        self._lcia_prev = {}
        self._lcia_baseline_ts = None
        self._lcia_baseline_lbl.config(
            text="Delta baseline cleared.  Next two LCIA runs will rebuild it.",
            fg=C_MUTED,
        )
        self._log("LCIA delta baseline cleared.")

    def _populate_lcia(self, impacts: list[tuple[str, float, str]]):
        # Save previous before overwriting
        prev = dict(self._lcia_prev)
        prev_ts = self._lcia_baseline_ts
        self._lcia_last = list(impacts)

        # Clear tree
        for iid in self._lcia_tree.get_children():
            self._lcia_tree.delete(iid)

        for name, amount, unit in impacts:
            is_gwp = any(k in name.lower()
                         for k in ("climate", "gwp", "co2", "global warm"))

            # Delta vs previous run for this category
            if name in prev and prev[name] != 0:
                pct = (amount - prev[name]) / prev[name] * 100
                delta_txt = f"{pct:+.2f}%"
            else:
                delta_txt = "--"
                pct = 0.0

            tags = []
            if is_gwp:
                tags.append("gwp")
            # Note: delta tag overrides the gwp color on the whole row.
            # For a small impact list this is fine; user mostly cares about
            # direction first, GWP highlight second.

            self._lcia_tree.insert(
                "", "end",
                text=name,
                values=(f"{amount:.6g}", unit or "--", delta_txt),
                tags=tags,
            )

        # Update baseline label - plain English
        now_ts = datetime.now().strftime("%H:%M:%S")
        if prev:
            self._lcia_baseline_lbl.config(
                text=(f"Comparing this run to LCIA from {prev_ts}.  "
                      f"This run is now the new baseline (run again to compare further)."),
                fg=C_TEXT,
            )
        else:
            self._lcia_baseline_lbl.config(
                text=(f"Last LCIA: {now_ts}.  "
                      f"Run again (after pushing changes) to see Δ vs prev."),
                fg=C_TEXT,
            )

        # Update baseline AFTER render
        self._lcia_prev = {name: amt for name, amt, _ in impacts}
        self._lcia_baseline_ts = now_ts

    # ==================================================================
    # TAB 3: MONTE CARLO (manual MC, click-to-select histogram)
    # ==================================================================

    def _build_mc_tab(self):
        tab = self._tab_mc

        top = tk.Frame(tab, bg=C_BG)
        top.pack(fill="x", padx=16, pady=8)

        _lbl(top, "Runs:", fg=C_MUTED).pack(side="left")
        self._mc_runs = tk.StringVar(value="100")
        tk.Spinbox(top, from_=10, to=2000, increment=10,
                   textvariable=self._mc_runs, width=7,
                   bg=C_SURFACE, fg=C_TEXT, buttonbackground=C_SURFACE,
                   insertbackground=C_TEXT, relief="flat",
                   font=("Courier", 10)).pack(side="left", padx=(4, 16))

        self._mc_run_btn = _btn(top, "Run Monte Carlo", self._mc_in_thread,
                                color=C_ACCENT2, fg=C_BG, bold=True, pad_x=16)
        self._mc_run_btn.pack(side="left")

        self._mc_cancel_btn = _btn(top, "Cancel", self._mc_cancel_run,
                                   color=C_ERROR, fg=C_BG, bold=True, pad_x=12)
        # Cancel hidden until a run starts; toggle in _mc_in_thread / _do_mc.

        _btn(top, "Export PNG",
             lambda: _save_fig_png(self._mc_fig, "monte_carlo.png")
             ).pack(side="left", padx=(12, 0))

        self._mc_status = tk.Label(top, text="",
                                   font=("Helvetica", 10),
                                   bg=C_BG, fg=C_MUTED)
        self._mc_status.pack(side="left", padx=12)

        # Explainer line - describe native MC behavior precisely.
        explain = tk.Label(
            tab,
            text=("Native OpenLCA Monte Carlo (server-side via client.simulate). "
                  "Resamples ALL exchanges with uncertainty defined - foreground "
                  "and background ecoinvent - plus parameters and characterization "
                  "factors with uncertainty. Distributions used are whatever is "
                  "stored on each exchange (normal, lognormal, triangle, uniform). "
                  "Click any row below to see that category's distribution."),
            bg=C_BG, fg=C_MUTED, font=("Helvetica", 8, "italic"),
            anchor="w", justify="left", wraplength=1400,
        )
        explain.pack(fill="x", padx=16, pady=(0, 4))

        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=8)

        self._mc_progress = ttk.Progressbar(tab, mode="determinate", length=400)

        # PanedWindow with draggable sash between table (left) and chart (right).
        body = ttk.PanedWindow(tab, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        left  = tk.Frame(body, bg=C_BG)
        right = tk.Frame(body, bg=C_BG)
        body.add(left,  weight=1)
        body.add(right, weight=1)

        # Treeview replaces the V6 grid layout. Columns are wider and resizable.
        # Order is now Mean / Unit / Std Dev (CV% dropped - it's std/mean and
        # gave no new info).
        self._mc_tree = ttk.Treeview(
            left,
            columns=("mean", "unit", "std"),
            show="tree headings", height=18,
        )
        self._mc_tree.heading("#0",   text="Impact Category")
        self._mc_tree.heading("mean", text="Mean")
        self._mc_tree.heading("unit", text="Unit")
        self._mc_tree.heading("std",  text="Std Dev")
        self._mc_tree.column("#0",   width=380, anchor="w", stretch=True)
        self._mc_tree.column("mean", width=120, anchor="e", stretch=False)
        self._mc_tree.column("unit", width=130, anchor="w", stretch=False)
        self._mc_tree.column("std",  width=110, anchor="e", stretch=False)

        sb = ttk.Scrollbar(left, orient="vertical", command=self._mc_tree.yview)
        self._mc_tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._mc_tree.pack(side="left", fill="both", expand=True)

        self._mc_tree.tag_configure("gwp", foreground=C_ACCENT2)
        # Click any row -> redraw the histogram for THAT category.
        self._mc_tree.bind("<<TreeviewSelect>>", self._on_mc_select)

        self._mc_fig, self._mc_canvas = _mpl_figure(right, figsize=(5.5, 3.5))
        self._mc_samples_by_cat: dict[str, list[float]] = {}
        self._mc_units_by_cat: dict[str, str] = {}
        self._mc_last_target: str | None = None
        # Map tree iid -> category name (we need this in the select handler
        # since the tree column shows the name but the iid is opaque).
        self._mc_iid_to_cat: dict[str, str] = {}

    def _populate_mc(self, impacts: list):
        # Clear tree
        for iid in self._mc_tree.get_children():
            self._mc_tree.delete(iid)

        self._mc_samples_by_cat = {r[0]: r[4] for r in impacts}
        self._mc_units_by_cat   = {r[0]: r[3] for r in impacts}
        self._mc_iid_to_cat     = {}

        for name, mean, std, unit, _samples in impacts:
            is_gwp = any(k in name.lower()
                         for k in ("climate", "gwp", "co2", "global warm"))
            tags = ("gwp",) if is_gwp else ()
            std_s = f"{std:.6g}" if std is not None else "--"
            iid = self._mc_tree.insert(
                "", "end",
                text=name,
                values=(f"{mean:.6g}", unit or "--", std_s),
                tags=tags,
            )
            self._mc_iid_to_cat[iid] = name

        # Default selection: GWP if present, else first row.
        target = next(
            (name for name, _, _, _, _ in impacts
             if any(k in name.lower()
                    for k in ("climate", "gwp", "co2", "global warm"))),
            impacts[0][0] if impacts else None,
        )
        self._mc_last_target = target
        if target:
            # Programmatically select the matching row so the user sees
            # which category the histogram is showing.
            for iid, cat in self._mc_iid_to_cat.items():
                if cat == target:
                    self._mc_tree.selection_set(iid)
                    self._mc_tree.see(iid)
                    break
            self._draw_mc_hist(target)

    def _on_mc_select(self, _event=None):
        sel = self._mc_tree.selection()
        if not sel:
            return
        cat = self._mc_iid_to_cat.get(sel[0])
        if cat:
            self._mc_last_target = cat
            self._draw_mc_hist(cat)

    def _draw_mc_hist(self, category: str):
        samples = self._mc_samples_by_cat.get(category, [])
        unit    = self._mc_units_by_cat.get(category, "")
        ax = self._mc_fig.axes[0]
        ax.clear()
        _restyle_axes_dark(ax)
        if samples:
            mean = statistics.fmean(samples)
            std  = statistics.pstdev(samples) if len(samples) > 1 else 0.0
            unique_vals = len(set(round(s, 12) for s in samples))

            if unique_vals <= 1 or std == 0.0:
                ax.text(
                    0.5, 0.5,
                    f"No variation across {len(samples)} runs\n"
                    f"all samples = {mean:.6g}\n\n"
                    f"Either no uncertainty is defined anywhere\n"
                    f"in the system, or the simulation is reading\n"
                    f"stale state. See the log for diagnostics.",
                    transform=ax.transAxes, ha="center", va="center",
                    color=C_WARN, fontsize=10,
                )
                ax.set_xticks([])
                ax.set_yticks([])
            else:
                ax.hist(samples, bins=min(30, max(10, len(samples) // 5)),
                        color=C_ACCENT2, edgecolor=C_BG)
                label = (f"mean = {mean:.3g}\nstd = {std:.3g}"
                         + (f"\nCV = {std/mean*100:.2f}%" if mean else ""))
                ax.axvline(mean, color=C_ACCENT3, linestyle="--",
                           linewidth=1.5, label=label)
                ax.legend(facecolor=C_BG, edgecolor=C_MUTED,
                          labelcolor=C_TEXT, fontsize=8)
                ax.set_xlabel(f"Impact amount{(' (' + unit + ')') if unit else ''}")
                ax.set_ylabel("Frequency")
        ax.set_title(f"MC distribution: {category[:60]}", fontsize=10)
        self._mc_fig.tight_layout()
        self._mc_canvas.draw()

    # ==================================================================
    # TAB 5: DIAGNOSTICS (std column + toggles)
    # ==================================================================

    def _build_diagnostics_tab(self):
        tab = self._tab_diag

        top = tk.Frame(tab, bg=C_BG, pady=8)
        top.pack(fill="x", padx=16)

        _lbl(top, "Filter:", fg=C_MUTED).pack(side="left")
        self._diag_filter = tk.StringVar()
        e = tk.Entry(top, textvariable=self._diag_filter, width=25,
                     bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                     relief="flat", font=("Helvetica", 10))
        e.pack(side="left", padx=(4, 8))
        e.bind("<KeyRelease>", lambda _e: self._populate_diag_tree(self._diag_all))

        # Toggle checkboxes
        self._diag_elec_only = tk.BooleanVar(value=False)
        self._diag_inputs_only = tk.BooleanVar(value=False)
        self._diag_show_std = tk.BooleanVar(value=True)

        for text, var in (
            ("Electricity only", self._diag_elec_only),
            ("Inputs only",      self._diag_inputs_only),
            ("Show std dev",     self._diag_show_std),
        ):
            tk.Checkbutton(
                top, text=text, variable=var,
                bg=C_BG, fg=C_TEXT, selectcolor=C_SURFACE,
                activebackground=C_BG, activeforeground=C_ACCENT,
                font=("Helvetica", 9),
                command=lambda: self._rebuild_diag_tree(),
            ).pack(side="left", padx=(4, 4))

        _btn(top, "Reload Process", self._diag_reload_in_thread).pack(side="left", padx=(12, 0))
        _btn(top, "Clear Log",      self._clear_log).pack(side="left", padx=(8, 0))
        _btn(top, "Open History",   self._open_history).pack(side="left", padx=(8, 0))

        body = tk.Frame(tab, bg=C_BG)
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # Tree container - rebuilt when 'show std' toggles to resize columns
        self._diag_tree_container = tk.Frame(body, bg=C_BG)
        self._diag_tree_container.pack(fill="both", expand=True, pady=(0, 8))
        self._diag_tree = None
        self._build_diag_tree()

        # Log console (bottom half)
        log_frame = tk.Frame(body, bg=C_BG)
        log_frame.pack(fill="both", expand=True)
        self._log_text = tk.Text(
            log_frame, height=10, bg=C_SURFACE, fg=C_TEXT,
            insertbackground=C_TEXT, relief="flat",
            font=("Courier", 9), wrap="none",
        )
        # Tag colors set ONCE here, not on every log line (V5 was rebuilding
        # them per-line, harmless but wasteful).
        self._log_text.tag_config("err",  foreground=C_ERROR)
        self._log_text.tag_config("warn", foreground=C_WARN)
        self._log_text.tag_config("ok",   foreground=C_OK)
        self._log_text.tag_config("info", foreground=C_TEXT)

        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_text.pack(side="left", fill="both", expand=True)

        self._diag_all: list[dict] = []
        self._log("Diagnostics ready.")

    def _build_diag_tree(self):
        """(Re)build the tree widget based on current 'show std' setting."""
        for w in self._diag_tree_container.winfo_children():
            w.destroy()

        show_std = self._diag_show_std.get()
        if show_std:
            cols = ("flow", "dir", "amount", "std", "unit", "desc")
            headings = (
                ("flow",   "Flow",        220),
                ("dir",    "Dir",          60),
                ("amount", "Amount",      110),
                ("std",    "Std Dev",     100),
                ("unit",   "Unit",         70),
                ("desc",   "Description", 240),
            )
        else:
            cols = ("flow", "dir", "amount", "unit", "desc")
            headings = (
                ("flow",   "Flow",        260),
                ("dir",    "Dir",          60),
                ("amount", "Amount",      130),
                ("unit",   "Unit",         80),
                ("desc",   "Description", 280),
            )

        self._diag_tree = ttk.Treeview(
            self._diag_tree_container, columns=cols,
            show="headings", height=14,
        )
        for col, label, width in headings:
            self._diag_tree.heading(col, text=label)
            self._diag_tree.column(col, width=width)
        self._diag_tree.pack(fill="both", expand=True)

    def _rebuild_diag_tree(self):
        self._build_diag_tree()
        self._populate_diag_tree(self._diag_all)

    # ==================================================================
    # PRODUCTS DIALOG
    # ==================================================================

    def _open_products_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Manage Products")
        dlg.configure(bg=C_BG)
        dlg.geometry("820x540")

        tk.Label(dlg, text="Registered Products",
                 bg=C_BG, fg=C_ACCENT,
                 font=("Helvetica", 12, "bold")
                 ).pack(anchor="w", padx=12, pady=(12, 4))

        # Top: list of products on left, editor on right
        top = tk.Frame(dlg, bg=C_BG)
        top.pack(fill="both", expand=True, padx=12, pady=4)

        # Left: listbox
        left = tk.Frame(top, bg=C_BG)
        left.pack(side="left", fill="y")
        lb = tk.Listbox(left, bg=C_SURFACE, fg=C_TEXT,
                        relief="flat", font=("Helvetica", 10),
                        selectbackground=C_ACCENT,
                        height=14, width=24)
        lb.pack(fill="y", expand=False)
        for p in self.products:
            lb.insert("end", p.name)

        # Right: editor fields
        right = tk.Frame(top, bg=C_BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        def _field(parent, label: str, var: tk.StringVar, width: int = 60):
            f = tk.Frame(parent, bg=C_BG)
            f.pack(fill="x", pady=2)
            tk.Label(f, text=label, width=18, anchor="w",
                     bg=C_BG, fg=C_MUTED,
                     font=("Helvetica", 9)).pack(side="left")
            tk.Entry(f, textvariable=var, width=width,
                     bg=C_SURFACE, fg=C_TEXT, insertbackground=C_TEXT,
                     relief="flat", font=("Courier", 9)
                     ).pack(side="left", fill="x", expand=True)

        name_v  = tk.StringVar()
        proc_v  = tk.StringVar()
        ps_v    = tk.StringVar()
        notes_v = tk.StringVar()

        _field(right, "Name:",              name_v)
        _field(right, "Process UUID:",      proc_v)
        _field(right, "Product System UUID:", ps_v)
        _field(right, "Notes:",             notes_v)

        # Exchanges editor - simple Text widget with JSON payload
        tk.Label(right, text="Exchanges (JSON array):",
                 bg=C_BG, fg=C_MUTED, font=("Helvetica", 9)
                 ).pack(anchor="w", pady=(8, 2))
        exch_text = tk.Text(right, height=12, bg=C_SURFACE, fg=C_TEXT,
                            insertbackground=C_TEXT, relief="flat",
                            font=("Courier", 9))
        exch_text.pack(fill="both", expand=True)
        hint = tk.Label(
            right,
            text=('Format: [{"display_name":"...","description_match":"...",'
                  '"default_mean":0.0,"default_std":0.0}, ...]'),
            bg=C_BG, fg=C_MUTED, font=("Helvetica", 8, "italic"),
        )
        hint.pack(anchor="w", pady=(2, 0))

        # Tracks which existing product is being edited (None for "new").
        # We can't rely on lb.curselection() at save time because the user
        # might have changed the name field - then the index in lb still
        # points at the original product but we need to replace it, not
        # create a duplicate. V5 had this bug.
        editing_idx = {"value": None}

        def _load_selected(_evt=None):
            sel = lb.curselection()
            if not sel:
                editing_idx["value"] = None
                return
            idx = sel[0]
            editing_idx["value"] = idx
            p = self.products[idx]
            name_v.set(p.name)
            proc_v.set(p.process_id)
            ps_v.set(p.product_system_id)
            notes_v.set(p.notes)
            exch_text.delete("1.0", "end")
            exch_text.insert("1.0",
                             json.dumps([e.to_dict() for e in p.exchanges], indent=2))

        lb.bind("<<ListboxSelect>>", _load_selected)
        if self.products:
            lb.selection_set(0)
            _load_selected()

        # Bottom: actions
        bot = tk.Frame(dlg, bg=C_BG)
        bot.pack(fill="x", padx=12, pady=8)

        def _gather() -> Product | None:
            try:
                exs = json.loads(exch_text.get("1.0", "end"))
                specs = [ExchangeSpec(**e) for e in exs]
            except Exception as e:
                messagebox.showerror("Bad exchanges JSON", str(e))
                return None
            if not name_v.get().strip():
                messagebox.showerror("Validation", "Name is required.")
                return None
            if not proc_v.get().strip():
                messagebox.showerror("Validation", "Process UUID is required.")
                return None
            return Product(
                name              = name_v.get().strip(),
                process_id        = proc_v.get().strip(),
                product_system_id = ps_v.get().strip(),
                exchanges         = specs,
                notes             = notes_v.get().strip(),
            )

        def _save():
            p = _gather()
            if not p:
                return
            idx = editing_idx["value"]
            if idx is not None:
                # Editing existing entry. If the name changed, also check
                # that the new name doesn't collide with a DIFFERENT entry.
                clash = next(
                    (i for i, q in enumerate(self.products)
                     if q.name == p.name and i != idx),
                    None,
                )
                if clash is not None:
                    messagebox.showerror(
                        "Name collision",
                        f"Another product is already named '{p.name}'. "
                        f"Choose a different name or delete the duplicate first.",
                    )
                    return
                old_name = self.products[idx].name
                self.products[idx] = p
                # Update listbox label if name changed
                if old_name != p.name:
                    lb.delete(idx)
                    lb.insert(idx, p.name)
                    lb.selection_set(idx)
            else:
                # New entry. Append unless name already exists.
                clash = next(
                    (i for i, q in enumerate(self.products) if q.name == p.name),
                    None,
                )
                if clash is not None:
                    if not messagebox.askyesno(
                        "Overwrite?",
                        f"A product named '{p.name}' already exists. Overwrite it?",
                    ):
                        return
                    self.products[clash] = p
                    editing_idx["value"] = clash
                else:
                    self.products.append(p)
                    lb.insert("end", p.name)
                    editing_idx["value"] = len(self.products) - 1
                    lb.selection_clear(0, "end")
                    lb.selection_set(editing_idx["value"])
            save_products(self.products)
            self._refresh_product_combo()
            self._log(f"Saved product '{p.name}'.", "ok")

        def _new():
            lb.selection_clear(0, "end")
            editing_idx["value"] = None
            name_v.set("New Product")
            proc_v.set("")
            ps_v.set("")
            notes_v.set("")
            exch_text.delete("1.0", "end")
            exch_text.insert("1.0", "[]")

        def _delete():
            sel = lb.curselection()
            if not sel:
                return
            p = self.products[sel[0]]
            if not messagebox.askyesno("Delete", f"Delete product '{p.name}'?"):
                return
            del self.products[sel[0]]
            save_products(self.products)
            lb.delete(sel[0])
            editing_idx["value"] = None
            self._refresh_product_combo()
            self._log(f"Deleted product '{p.name}'.", "warn")

        _btn(bot, "New",    _new,    color=C_SURFACE).pack(side="left", padx=(0, 8))
        _btn(bot, "Save",   _save,   color=C_ACCENT, fg=C_BG, bold=True).pack(side="left")
        _btn(bot, "Delete", _delete, color=C_ERROR,  fg=C_BG, bold=True).pack(side="left", padx=(8, 0))
        _btn(bot, "Close",  dlg.destroy).pack(side="right")

    def _refresh_product_combo(self):
        names = [p.name for p in self.products]
        self._product_combo.configure(values=names)
        if self._product_var.get() not in names and names:
            self._product_var.set(names[0])
            self._on_product_change()

    def _on_product_change(self):
        name = self._product_var.get()
        p = next((q for q in self.products if q.name == name), None)
        if not p:
            return
        self.current_product = p
        self.settings["last_product"] = name
        save_settings(self.settings)
        self._build_exchange_rows()
        self._log(f"Switched to product '{name}'.")

        # Auto-select the product's Product System if registered. Helps the
        # user understand the link between Product (local entry) and Product
        # System (OpenLCA calculation graph).
        if p.product_system_id and self._ps_map:
            ps_name = next(
                (n for n, uid in self._ps_map.items() if uid == p.product_system_id),
                None,
            )
            if ps_name and self._ps_var.get() != ps_name:
                self._ps_var.set(ps_name)
                self._log(f"Auto-selected Product System: {ps_name}")

        # fetch current values for new product
        if self.client:
            self._refresh_in_thread()

    # ==================================================================
    # UI-THREAD MARSHALLING
    # ==================================================================

    def _ui(self, fn, *args, **kwargs):
        self._ui_queue.put(lambda: fn(*args, **kwargs))

    def _drain_ui_queue(self):
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as e:
                    try:
                        self._log(f"UI error: {e}", "error")
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queue)

    # ==================================================================
    # LOGGING
    # ==================================================================

    def _log(self, msg: str, level: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        color_tag = {"error": "err", "warn": "warn", "ok": "ok"}.get(level, "info")
        line = f"[{ts}] {msg}\n"

        def _append():
            # Tags configured at log_text construction; don't redo on every line.
            self._log_text.insert("end", line, color_tag)
            self._log_text.see("end")
        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self._ui(_append)

    def _clear_log(self):
        self._log_text.delete("1.0", "end")

    def _open_history(self):
        if not HISTORY_FILE.exists():
            messagebox.showinfo("History",
                                f"No history yet.\nWill be written to:\n{HISTORY_FILE}")
            return
        messagebox.showinfo("History", f"Session history:\n{HISTORY_FILE}")

    # ==================================================================
    # CONNECTION + REFRESH
    # ==================================================================

    def _current_url(self) -> str:
        host = self._host_var.get().strip() or "localhost"
        try:
            port = int(self._port_var.get())
        except ValueError:
            port = 8080
        return f"http://{host}:{port}"

    def _connect_and_refresh(self):
        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        # persist any host/port edits
        host = self._host_var.get().strip() or "localhost"
        try:
            port = int(self._port_var.get())
        except ValueError:
            port = 8080
        self.settings["host"] = host
        self.settings["port"] = port
        save_settings(self.settings)

        url = self._current_url()
        self._set_status(f"Connecting to {url}...", C_WARN)
        self._log(f"Connecting to OpenLCA IPC at {url}...")

        # Step 1: TCP-level reachability. The IPC client is lazy and won't
        # tell us the server is unreachable until the first real call -
        # so we probe the socket ourselves before claiming Connected.
        ok, reason = check_server_reachable(host, port, timeout=3.0)
        if not ok:
            self.client = None
            msg = f"Cannot reach {url}: {reason}"
            self._set_status(msg, C_ERROR)
            self._log(msg, "error")
            return

        # Step 2: Construct client and verify with a real IPC call.
        try:
            self.client = make_client(host, port)
            # Lightweight verification: any single API call. If the server
            # is at the URL but not an OpenLCA IPC server, this raises.
            list(self.client.get_descriptors(o.ImpactMethod))
        except Exception as e:
            self.client = None
            msg = f"IPC handshake failed: {e}"
            self._set_status(msg, C_ERROR)
            self._log(msg, "error")
            return

        self._set_status(f"Connected - {url}", C_OK)
        self._log(f"Connected to {url}.", "ok")
        # Surface olca-ipc package version - useful when diagnosing MC issues
        # since simulate_next behavior has changed across versions.
        try:
            import importlib.metadata as _md
            ver = _md.version("olca-ipc")
            self._log(f"olca-ipc version: {ver}")
        except Exception:
            pass
        self._do_load_descriptors()
        self._do_refresh()
        self._do_diag_reload()

    def _load_descriptors_in_thread(self):
        if not self._require_client():
            return
        threading.Thread(target=self._do_load_descriptors, daemon=True).start()

    def _do_load_descriptors(self):
        try:
            ps      = get_descriptors(self.client, o.ProductSystem)
            methods = get_descriptors(self.client, o.ImpactMethod)

            self._ps_map = {name: uid for uid, name in ps}
            self._ui(lambda: self._ps_combo.configure(values=list(self._ps_map)))
            # Pre-select the product's PS if it matches
            pref = self.current_product.product_system_id
            pref_name = next((n for u, n in ps if u == pref), None)
            if pref_name:
                self._ui(lambda: self._ps_var.set(pref_name))
            elif ps and not self._ps_var.get():
                self._ui(lambda: self._ps_var.set(ps[0][1]))

            self._method_map = {name: uid for uid, name in methods}
            self._ui(lambda: self._method_combo.configure(values=list(self._method_map)))
            if methods and not self._method_var.get():
                self._ui(lambda: self._method_var.set(methods[0][1]))

            self._log(f"Loaded {len(ps)} product systems, {len(methods)} methods.", "ok")
        except Exception as e:
            self._set_status(f"Descriptor load failed: {e}", C_WARN)
            self._log(f"Descriptor load failed: {e}", "error")

    def _refresh_in_thread(self):
        if not self._require_client():
            return
        gen = self._row_gen
        threading.Thread(target=self._do_refresh, args=(gen,), daemon=True).start()

    def _do_refresh(self, gen: int = 0):
        self._set_status("Fetching current values...", C_WARN)
        try:
            live = get_current_values(self.client, self.current_product.process_id)
            if gen == self._row_gen:
                for row in self.row_widgets:
                    spec = row["spec"]
                    match  = next((v for k, v in live.items()
                                   if spec.description_match.lower() in k.lower()), None)
                    text = f"{match:.6f}" if match is not None else "not found"
                    self._ui(row["current_var"].set, text)
            self._set_status(f"Connected - {self._current_url()}", C_OK)
            self._log(f"Refreshed {len(live)} live values for '{self.current_product.name}'.")
        except Exception as e:
            self._set_status(f"Refresh failed: {e}", C_ERROR)
            self._log(f"Refresh failed: {e}", "error")

    # ==================================================================
    # EXCHANGES: PUSH
    # ==================================================================

    def _collect_values(self) -> tuple[dict, dict] | None:
        """
        Returns (values, part_ids) or None on error.
        values: {display_name: (mean, std_or_None)}
        part_ids: {display_name: part_id_string}  (only populated in specific mode)
        """
        values: dict[str, tuple[float, float | None]] = {}
        part_ids: dict[str, str] = {}
        specific = (self._push_mode.get() == "specific")
        for row in self.row_widgets:
            try:
                mean = float(row["new_var"].get())
            except ValueError:
                messagebox.showerror("Bad input",
                                     f"Invalid number for {row['desc']}.")
                return None
            if specific:
                std = None
            else:
                try:
                    std = float(row["std_var"].get())
                except ValueError:
                    messagebox.showerror("Bad input",
                                         f"Invalid std for {row['desc']}.")
                    return None
            values[row["desc"]] = (mean, std)
            if specific:
                pid = (row["part_var"].get() or "").strip()
                if pid:
                    part_ids[row["desc"]] = pid
        return values, part_ids

    def _push_all_in_thread(self):
        if not self._require_client():
            return
        res = self._collect_values()
        if res is None:
            return
        values, part_ids = res

        self._ui(self._push_all_lbl.config, text="Pushing...", fg=C_WARN)
        for row in self.row_widgets:
            self._ui(row["status_var"].set, "...")
            self._ui(row["status_lbl"].config, fg=C_WARN)

        gen = self._row_gen
        threading.Thread(target=self._do_push_all,
                         args=(values, part_ids, gen), daemon=True).start()

    def _do_push_all(self, values: dict, part_ids: dict, gen: int):
        # warn_cb forwards ambiguous-match warnings into the GUI log
        def _warn(msg: str):
            self._log(msg, "warn")
        try:
            res = push_all(
                self.client, self.current_product.process_id,
                self.current_product, values, warn_cb=_warn,
            )
            # If the user switched products mid-push, our row references
            # are stale - skip per-row UI updates but still log+history.
            if gen == self._row_gen:
                for row in self.row_widgets:
                    d = row["desc"]
                    if d in res["updated"]:
                        old = res["updated"][d]
                        new = values[d][0]
                        self._ui(row["current_var"].set, f"{new:.6f}")
                        self._ui(row["status_var"].set, f"OK ({old:.4f}->{new:.4f})")
                        self._ui(row["status_lbl"].config, fg=C_OK)
                    elif d in res["not_found"]:
                        self._ui(row["status_var"].set, "NOT FOUND")
                        self._ui(row["status_lbl"].config, fg=C_ERROR)
            n_ok  = len(res["updated"])
            n_bad = len(res["not_found"])
            if gen == self._row_gen:
                self._ui(self._push_all_lbl.config,
                         text=f"Done - {n_ok} pushed, {n_bad} not found",
                         fg=C_OK if n_bad == 0 else C_WARN)
            self._log(f"Push All ({self._push_mode.get()}): {n_ok} updated, {n_bad} not found.",
                      "ok" if n_bad == 0 else "warn")
            append_history({
                "event":    "push_all",
                "product":  self.current_product.name,
                "mode":     self._push_mode.get(),
                "updated":  n_ok,
                "not_found": n_bad,
                "part_ids": part_ids if part_ids else None,
            })
        except Exception as e:
            if gen == self._row_gen:
                self._ui(self._push_all_lbl.config, text=f"Push All failed: {e}", fg=C_ERROR)
            self._log(f"Push All failed: {e}", "error")

    def _push_row(self, desc, new_var, std_var, part_var, status_lbl, status_var):
        if not self._require_client():
            return
        specific = (self._push_mode.get() == "specific")
        try:
            mean = float(new_var.get())
        except ValueError:
            status_var.set("Bad input")
            status_lbl.config(fg=C_ERROR)
            return
        if specific:
            std = None
            pid = (part_var.get() or "").strip()
        else:
            try:
                std = float(std_var.get())
            except ValueError:
                status_var.set("Bad std")
                status_lbl.config(fg=C_ERROR)
                return
            pid = ""
        status_var.set("Pushing...")
        status_lbl.config(fg=C_WARN)

        gen = self._row_gen
        def _warn(msg: str):
            self._log(msg, "warn")

        def _do():
            try:
                old = push_one(
                    self.client, self.current_product.process_id,
                    self.current_product, desc, mean, std,
                    warn_cb=_warn,
                )
                if gen == self._row_gen:
                    for row in self.row_widgets:
                        if row["desc"] == desc:
                            self._ui(row["current_var"].set, f"{mean:.6f}")
                            break
                    self._ui(status_var.set, f"OK  ({old:.4f}->{mean:.4f})")
                    self._ui(status_lbl.config, fg=C_OK)
                self._log(f"Pushed {desc} ({self._push_mode.get()}): "
                          f"{old:.4f} -> {mean:.4f}" + (f"  part={pid}" if pid else ""), "ok")
                append_history({
                    "event":   "push_one",
                    "product": self.current_product.name,
                    "mode":    self._push_mode.get(),
                    "name":    desc,
                    "old":     old,
                    "new":     mean,
                    "std":     std,
                    "part_id": pid or None,
                })
            except Exception as e:
                if gen == self._row_gen:
                    self._ui(status_var.set, "Failed")
                    self._ui(status_lbl.config, fg=C_ERROR)
                    self._ui(messagebox.showerror, "Push failed", f"{desc}: {e}")
                self._log(f"Push failed for {desc}: {e}", "error")

        threading.Thread(target=_do, daemon=True).start()

    # ==================================================================
    # CSV I/O
    # ==================================================================

    def _import_csv(self):
        path = filedialog.askopenfilename(
            title="Import exchanges CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            vals, part_ids = import_exchanges_csv(path)
        except Exception as e:
            messagebox.showerror("Import failed", str(e))
            return
        applied = 0
        known_names = {row["desc"] for row in self.row_widgets}
        for row in self.row_widgets:
            if row["desc"] in vals:
                m, s = vals[row["desc"]]
                row["new_var"].set(f"{m:.6f}")
                if s is not None:
                    row["std_var"].set(f"{s:.6f}")
                if row["desc"] in part_ids:
                    row["part_var"].set(part_ids[row["desc"]])
                applied += 1

        # Find rows in CSV that have no matching exchange in the current product
        unmatched = [name for name in vals if name not in known_names]
        # Find current rows that the CSV didn't supply a value for
        not_in_csv = [name for name in known_names if name not in vals]

        msg = f"Applied {applied} of {len(self.row_widgets)} rows."
        if unmatched:
            msg += (f"\n\n{len(unmatched)} CSV row(s) had no matching "
                    f"exchange in '{self.current_product.name}' and were "
                    f"skipped:\n  - " + "\n  - ".join(unmatched[:10]))
            if len(unmatched) > 10:
                msg += f"\n  ... and {len(unmatched) - 10} more"
        if not_in_csv:
            msg += (f"\n\n{len(not_in_csv)} exchange(s) in the current "
                    f"product were not in the CSV (kept previous values):"
                    f"\n  - " + "\n  - ".join(not_in_csv[:10]))
            if len(not_in_csv) > 10:
                msg += f"\n  ... and {len(not_in_csv) - 10} more"
        msg += "\n\nClick 'Push All' to send to OpenLCA."

        self._log(f"Imported {applied} rows from {path} "
                  f"({len(unmatched)} unmatched, {len(not_in_csv)} missing).",
                  "ok" if not unmatched else "warn")
        messagebox.showinfo("Import", msg)

    def _export_exchanges_csv(self):
        res = self._collect_values()
        if res is None:
            return
        values, part_ids = res
        path = filedialog.asksaveasfilename(
            title="Export exchanges CSV", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            export_exchanges_csv(path, values, part_ids)
            self._log(f"Exported exchanges to {path}.", "ok")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _export_impacts_csv(self):
        if not self._lcia_last:
            messagebox.showinfo("No data", "Run an LCIA first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export impacts CSV", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            export_impacts_csv(path, self._lcia_last)
            self._log(f"Exported impacts to {path}.", "ok")
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    # ==================================================================
    # LCIA
    # ==================================================================

    def _lcia_in_thread(self):
        if not self._require_client():
            return
        ps_id, method_id = self._selected_ids()
        if not ps_id or not method_id:
            messagebox.showerror("Config needed",
                                 "Select a Product System and LCIA Method above.")
            return
        self._ui(self._lcia_status.config, text="Calculating...", fg=C_WARN)
        self._log("Running LCIA...")
        threading.Thread(target=self._do_lcia, args=(ps_id, method_id),
                         daemon=True).start()

    def _do_lcia(self, ps_id: str, method_id: str):
        try:
            impacts = run_lcia_full(self.client, ps_id, method_id)
            self._ui(self._populate_lcia, impacts)
            self._ui(self._lcia_status.config,
                     text=f"{len(impacts)} categories", fg=C_OK)
            self._log(f"LCIA done: {len(impacts)} categories.", "ok")
            append_history({"event": "lcia",
                            "product": self.current_product.name,
                            "n_categories": len(impacts)})
        except Exception as e:
            self._ui(self._lcia_status.config, text=str(e), fg=C_ERROR)
            self._log(f"LCIA failed: {e}", "error")

    # ==================================================================
    # MONTE CARLO
    # ==================================================================

    def _mc_in_thread(self):
        if not self._require_client():
            return
        ps_id, method_id = self._selected_ids()
        if not ps_id or not method_id:
            messagebox.showerror("Config needed",
                                 "Select a Product System and LCIA Method above.")
            return
        try:
            n = int(self._mc_runs.get())
        except ValueError:
            messagebox.showerror("Bad input", "Run count must be an integer.")
            return

        # Pre-flight: how many exchanges in the foreground process have
        # uncertainty defined? If zero, the user almost certainly forgot
        # to Push All in Population avg mode. Background ecoinvent
        # uncertainty is checked server-side at simulation time, so this
        # is a best-effort foreground sanity check only.
        try:
            n_unc, n_total = count_uncertainty_in_process(
                self.client, self.current_product.process_id,
            )
        except Exception as e:
            messagebox.showerror("Pre-flight failed",
                                 f"Could not inspect process: {e}")
            return

        self._log(f"Pre-flight: {n_unc} of {n_total} exchanges in foreground "
                  f"process have uncertainty defined.")
        if n_unc == 0:
            if not messagebox.askyesno(
                "No foreground uncertainty",
                f"None of the {n_total} exchanges in the foreground process "
                f"have uncertainty defined. Native OpenLCA MC will only "
                f"vary background (ecoinvent) and characterization-factor "
                f"uncertainty.\n\n"
                f"To include foreground variation, switch to the Exchanges "
                f"tab, set std > 0, and Push All in 'Population avg' mode.\n\n"
                f"Run MC anyway?",
            ):
                return

        self._mc_cancel.clear()
        self._ui(self._mc_status.config,
                 text=f"Starting {n} runs (native MC)...", fg=C_WARN)
        self._mc_progress["maximum"] = n
        self._mc_progress["value"]   = 0
        self._mc_progress.pack(padx=16, pady=(0, 4))
        self._mc_run_btn.pack_forget()
        self._mc_cancel_btn.pack(side="left", before=self._mc_status)
        self._log(f"Native Monte Carlo starting: {n} runs.")
        threading.Thread(target=self._do_mc,
                         args=(ps_id, method_id, n, n_unc, n_total),
                         daemon=True).start()

    def _mc_cancel_run(self):
        """User clicked Cancel - signal the worker thread to stop cleanly."""
        self._mc_cancel.set()
        self._ui(self._mc_status.config,
                 text="Cancelling at next iteration...", fg=C_WARN)
        self._log("Monte Carlo cancel requested.", "warn")

    def _do_mc(self, ps_id: str, method_id: str, n: int,
               n_unc: int, n_total: int):
        def progress(current, total):
            self._ui(lambda c=current, t=total: (
                self._mc_progress.configure(value=c),
                self._mc_status.config(text=f"Run {c}/{t}...", fg=C_WARN),
            ))

        def mc_log(msg: str):
            level = "warn" if msg.startswith("WARNING") else "info"
            self._log(msg, level)

        def _restore_buttons():
            self._mc_progress.pack_forget()
            self._mc_cancel_btn.pack_forget()
            self._mc_run_btn.pack(side="left", before=self._mc_status)

        try:
            impacts = run_monte_carlo(
                self.client,
                ps_id, method_id,
                n_runs=n,
                progress_cb=progress, log_cb=mc_log,
                cancel_event=self._mc_cancel,
            )
            self._ui(_restore_buttons)
            self._ui(self._populate_mc, impacts)

            cancelled = self._mc_cancel.is_set()
            actual_runs = len(impacts[0][4]) if impacts else 0

            n_zero = sum(1 for _, _, std, _, _ in impacts if std == 0.0)
            n_total_cats = len(impacts)
            if cancelled:
                self._ui(self._mc_status.config,
                         text=f"Cancelled - {n_total_cats} cats from {actual_runs} runs",
                         fg=C_WARN)
            elif impacts and n_zero == n_total_cats:
                self._ui(self._mc_status.config,
                         text=f"{n_total_cats} cats, ALL std=0 - see log!",
                         fg=C_ERROR)
            elif n_zero > 0:
                self._ui(self._mc_status.config,
                         text=f"{n_total_cats} cats ({actual_runs} runs) | {n_zero} with std=0",
                         fg=C_WARN)
            else:
                self._ui(self._mc_status.config,
                         text=f"{n_total_cats} categories  ({actual_runs} runs)", fg=C_OK)
            self._log(
                f"Native Monte Carlo {'cancelled' if cancelled else 'done'}: "
                f"{n_total_cats} categories, {actual_runs} of {n} runs.",
                "warn" if cancelled else "ok",
            )
            append_history({"event": "monte_carlo_native",
                            "product": self.current_product.name,
                            "n_runs_requested": n,
                            "n_runs_actual": actual_runs,
                            "cancelled": cancelled,
                            "n_categories": n_total_cats,
                            "n_zero_std": n_zero,
                            "n_foreground_unc": n_unc,
                            "n_foreground_total": n_total,
                            })
        except Exception as e:
            self._ui(_restore_buttons)
            self._ui(self._mc_status.config, text=str(e), fg=C_ERROR)
            self._log(f"Native Monte Carlo failed: {e}", "error")

    # ==================================================================
    # DIAGNOSTICS
    # ==================================================================

    def _diag_reload_in_thread(self):
        if not self._require_client():
            return
        threading.Thread(target=self._do_diag_reload, daemon=True).start()

    def _do_diag_reload(self):
        try:
            rows = list_all_exchanges(self.client, self.current_product.process_id)
            self._diag_all = rows
            self._ui(self._populate_diag_tree, rows)
            self._log(f"Diagnostics: loaded {len(rows)} exchanges for "
                      f"'{self.current_product.name}'.")
        except Exception as e:
            self._log(f"Diagnostics reload failed: {e}", "error")

    def _populate_diag_tree(self, rows: list[dict]):
        for iid in self._diag_tree.get_children():
            self._diag_tree.delete(iid)
        flt = (self._diag_filter.get() or "").strip().lower()
        elec_only   = self._diag_elec_only.get()
        inputs_only = self._diag_inputs_only.get()
        show_std    = self._diag_show_std.get()

        for r in rows:
            if elec_only and not r["is_electricity"]:
                continue
            if inputs_only and r["direction"] != "input":
                continue
            if flt and not (
                flt in r["flow"].lower()
                or flt in r["description"].lower()
                or flt in r["direction"].lower()
            ):
                continue
            std_s = "--" if r["std"] is None else f"{r['std']:.6g}"
            if show_std:
                values = (r["flow"], r["direction"],
                          f"{r['amount']:.6g}", std_s,
                          r["unit"], r["description"])
            else:
                values = (r["flow"], r["direction"],
                          f"{r['amount']:.6g}",
                          r["unit"], r["description"])
            self._diag_tree.insert("", "end", values=values)

    # ==================================================================
    # UTILITIES
    # ==================================================================

    def _require_client(self) -> bool:
        if self.client:
            return True
        messagebox.showerror("Not connected", "No active server connection.")
        return False

    def _selected_ids(self) -> tuple:
        return (
            self._ps_map.get(self._ps_var.get()),
            self._method_map.get(self._method_var.get()),
        )

    def _set_status(self, text: str, color: str):
        self._ui(self._status_lbl.config, text=text, fg=color)


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()
 