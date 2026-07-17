"""Integration tests against a live OpenLCA + IPC.

Requires OpenLCA running with the oil pump database loaded and IPC on 8081.
Reference values come from §13 of the design doc (oil pump V1, TRACI 2.1).

Run:
    pytest tests/test_tools.py -v -s

If OpenLCA isn't running, every test will skip rather than fail.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.health import ping_server
from tools.systems import list_product_systems, get_product_system
from tools.lcia import (
    list_impact_methods,
    calculate_product_system,
    get_impact_contributions,
)
from tools.inventory import list_processes


def _require_ipc():
    out = ping_server()
    if not out.get("ok"):
        pytest.skip(f"OpenLCA IPC not available: {out.get('error')}")


# ---------- Health and listing ----------

def test_ping_returns_ok():
    _require_ipc()
    out = ping_server()
    assert out["ok"] is True
    assert out["product_system_count"] >= 1


def test_list_product_systems_finds_oil_pump():
    _require_ipc()
    out = list_product_systems()
    assert "systems" in out
    names = [s["name"].lower() for s in out["systems"]]
    assert any("oil pump" in n for n in names), f"Oil pump system missing. Got: {names}"


def test_get_product_system_serializes_cleanly():
    """Regression test for the to_json()/to_dict() shape bug: fetch one
    product system and confirm nested fields came back as JSON-serializable
    dicts/primitives, not raw olca_schema objects. Before the fix, this
    would have fallen through to dict(ps.__dict__), leaving fields like
    ref_process/ref_exchange as non-serializable objects (json.dumps would
    still "work" downstream via default=str, but as an opaque repr string
    instead of structured data -- this test catches that directly rather
    than relying on eyeballing the output)."""
    _require_ipc()
    systems = list_product_systems()["systems"]
    if not systems:
        pytest.skip("No product systems in this database")
    data = get_product_system(systems[0]["id"])
    assert "error" not in data, f"get_product_system errored: {data}"
    assert data.get("name"), "expected a name field"
    try:
        json.dumps(data)
    except TypeError as e:
        pytest.fail(
            f"get_product_system's result is not directly JSON-serializable "
            f"(fell back to a non-recursive serialization path): {e}"
        )
    # Spot-check one commonly-present nested field, if the fixture database
    # has it populated: it must be a dict (id/name), not an object repr string.
    ref_process = data.get("ref_process") or data.get("refProcess")
    if ref_process is not None:
        assert isinstance(ref_process, dict), (
            f"ref_process should be a nested dict, got {type(ref_process).__name__}: "
            f"{ref_process!r}"
        )


def test_list_impact_methods_finds_traci():
    _require_ipc()
    out = list_impact_methods()
    assert "methods" in out
    assert out["count"] >= 1
    names = [m["name"].lower() for m in out["methods"]]
    assert any("traci" in n for n in names), "TRACI method missing"


# ---------- Calculation reference values (§13) ----------

EXPECTED_CLIMATE_CHANGE_KG_CO2 = 32.32
TOLERANCE_PCT = 0.05  # 5% wiggle room for any background-data drift


def _find_oil_pump_id():
    for s in list_product_systems()["systems"]:
        if "oil pump" in s["name"].lower() and "v1" in s["name"].lower():
            return s["id"]
    pytest.skip("Oil Pump V1 not in this database")


def _find_traci_id():
    for m in list_impact_methods()["methods"]:
        n = m["name"].lower()
        if "traci" in n and "2.1" in n:
            return m["id"]
    pytest.skip("TRACI 2.1 not in this database")


def test_calculate_oil_pump_traci_climate_change():
    _require_ipc()
    ps_id = _find_oil_pump_id()
    method_id = _find_traci_id()

    out = calculate_product_system(ps_id, method_id)
    assert "impacts" in out, f"Got error or unexpected shape: {out}"

    climate = next(
        (i for i in out["impacts"] if "climate" in i["category"].lower()),
        None,
    )
    assert climate is not None, f"No climate category in {[i['category'] for i in out['impacts']]}"

    expected = EXPECTED_CLIMATE_CHANGE_KG_CO2
    actual = climate["amount"]
    rel_err = abs(actual - expected) / expected
    assert rel_err < TOLERANCE_PCT, (
        f"Climate change {actual} kg CO2-Eq differs from §13 reference "
        f"{expected} kg CO2-Eq by {rel_err:.1%}"
    )
    assert "co2" in climate["unit"].lower()


def test_get_impact_contributions_oil_pump():
    """Smoke test for the contribution shape probe (§14 open risk).

    Does not check specific contributors; just that the call returns a list
    of dicts with the expected keys. If this fails on shape, lcia.py needs
    its access path adjusted.
    """
    _require_ipc()
    ps_id = _find_oil_pump_id()
    method_id = _find_traci_id()

    impacts = calculate_product_system(ps_id, method_id)["impacts"]
    climate = next(i for i in impacts if "climate" in i["category"].lower())

    out = get_impact_contributions(ps_id, method_id, climate["category_id"])
    assert "contributions" in out, f"Got error or unexpected shape: {out}"
    assert out["total_returned"] > 0
    first = out["contributions"][0]
    assert {"process", "amount"} <= set(first.keys())


# ---------- Inventory ----------

def test_list_processes_with_keyword():
    _require_ipc()
    out = list_processes("aluminium")
    assert "processes" in out
    assert out["returned"] <= 50
    # Exact substring match is expected for this keyword against a real
    # ecoinvent-style database, so fuzzy_match should be False here -- but
    # only assert the literal-substring property when it actually is an
    # exact match. A fuzzy fallback (see tools/inventory.py::_search_processes)
    # can legitimately return names that don't contain the keyword verbatim
    # (that's the point of it), so asserting substring containment
    # unconditionally would fail on a correctly-working fuzzy result.
    if out["returned"] > 0 and not out.get("fuzzy_match"):
        assert all("aluminium" in p["name"].lower() for p in out["processes"])


def test_list_processes_fuzzy_fallback_on_misspelling():
    """US spelling against a database that (per test_list_processes_with_keyword)
    uses UK/database spelling "aluminium" should have zero exact hits and
    fall back to fuzzy matching -- exercises the fallback against a live
    database, which tests/test_inventory.py's fake descriptors cannot."""
    _require_ipc()
    out = list_processes("aluminum")  # US spelling, deliberately not in the DB
    assert "processes" in out
    if out["returned"] > 0:
        assert out["fuzzy_match"] is True, (
            "expected the US-spelling query to only find matches via the "
            f"fuzzy fallback, got fuzzy_match={out.get('fuzzy_match')}"
        )
