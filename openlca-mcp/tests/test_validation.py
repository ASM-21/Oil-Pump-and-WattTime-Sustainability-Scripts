"""Unit tests for UUID validation and registry. No IPC required.

    pytest tests/test_validation.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation import UUID_RE, UuidRegistry, validate_args


# ---------- Regex sanity ----------

def test_uuid_regex_accepts_canonical():
    assert UUID_RE.match("eb8d30cc-1410-42c5-8dd2-8c1f82d289ec")


def test_uuid_regex_accepts_uppercase():
    assert UUID_RE.match("EB8D30CC-1410-42C5-8DD2-8C1F82D289EC")


def test_uuid_regex_rejects_short():
    assert not UUID_RE.match("eb8d30cc")


def test_uuid_regex_rejects_invented_prefix():
    assert not UUID_RE.match("psys-1")
    assert not UUID_RE.match("method-traci")


# ---------- Format-only validation (no registry) ----------

def test_validate_args_passes_well_formed():
    args = {
        "product_system_id": "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec",
        "method_id": "1ac50550-a158-40f3-8f31-0c5473d9f08f",
    }
    # No registry passed - format check only
    assert validate_args("calculate_product_system", args) is None


def test_validate_args_rejects_invented_uuid():
    args = {"product_system_id": "oil-pump-v1"}
    err = validate_args("get_product_system", args)
    assert err is not None
    assert "list_product_systems" in err["error"]


def test_validate_args_directs_to_calculate_for_category():
    args = {"impact_category_id": "climate-change"}
    err = validate_args("get_impact_contributions", args)
    assert err is not None
    assert "calculate_product_system" in err["error"]


def test_validate_args_ignores_non_uuid_fields():
    args = {"keyword": "transport"}
    assert validate_args("list_processes", args) is None


def test_validate_args_skips_empty_values():
    args = {"product_system_id": ""}
    assert validate_args("get_product_system", args) is None


def test_validate_args_rejects_non_dict():
    err = validate_args("ping_server", "not a dict")
    assert err is not None


# ---------- Registry tracking ----------

def test_registry_starts_empty():
    r = UuidRegistry()
    assert r.product_systems == set()
    assert r.methods == set()
    assert r.categories == set()
    assert r.processes == set()
    assert r.all == set()


def test_registry_tracks_product_systems():
    r = UuidRegistry()
    r.track_result(
        "list_product_systems",
        {"systems": [
            {"id": "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec", "name": "Oil Pump V1"},
            {"id": "099e999b-4db3-4b72-8712-ed5abb3dd785", "name": "Oil Pump"},
        ]},
    )
    assert "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec" in r.product_systems
    assert "099e999b-4db3-4b72-8712-ed5abb3dd785" in r.product_systems
    assert r.methods == set()
    # Also in the "all" superset
    assert "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec" in r.all


def test_registry_tracks_methods_and_categories():
    r = UuidRegistry()
    r.track_result(
        "list_impact_methods",
        {"methods": [{"id": "1ac50550-a158-40f3-8f31-0c5473d9f08f", "name": "TRACI v2.1"}]},
    )
    r.track_result(
        "calculate_product_system",
        {"impacts": [
            {"category": "Climate change",
             "category_id": "7b5ff54f-aaaa-bbbb-cccc-111122223333",
             "amount": 32.32, "unit": "kg CO2-Eq"},
        ]},
    )
    assert "1ac50550-a158-40f3-8f31-0c5473d9f08f" in r.methods
    assert "7b5ff54f-aaaa-bbbb-cccc-111122223333" in r.categories


def test_registry_normalizes_case():
    r = UuidRegistry()
    r.track_result(
        "list_product_systems",
        {"systems": [{"id": "EB8D30CC-1410-42C5-8DD2-8C1F82D289EC", "name": "X"}]},
    )
    assert r.is_known_for("product_system_id", "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec")
    assert r.is_known_for("product_system_id", "EB8D30CC-1410-42C5-8DD2-8C1F82D289EC")


def test_registry_clear():
    r = UuidRegistry()
    r.track_result("list_product_systems", {"systems": [{"id": "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec"}]})
    r.clear()
    assert not r.is_known_for("product_system_id", "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec")


# ---------- Type-aware registry validation ----------

def test_registry_blocks_invented_uuid():
    """The exact failure mode from Andrew's session - well-formed but never seen."""
    r = UuidRegistry()
    r.track_result(
        "list_product_systems",
        {"systems": [{"id": "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec", "name": "Oil Pump V1"}]},
    )
    r.track_result(
        "list_impact_methods",
        {"methods": [{"id": "1ac50550-a158-40f3-8f31-0c5473d9f08f", "name": "TRACI v2.1"}]},
    )
    args = {
        "product_system_id": "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec",
        "method_id": "6a98a41c-f241-427f-84f0-42cf242d5443",  # invented
    }
    err = validate_args("calculate_product_system", args, r)
    assert err is not None
    assert "Unknown UUID" in err["error"]
    assert "method_id" in err["error"]


def test_registry_blocks_type_mismatch():
    """Using a method UUID where a product_system UUID is expected."""
    r = UuidRegistry()
    method_id = "1ac50550-a158-40f3-8f31-0c5473d9f08f"
    r.track_result("list_impact_methods", {"methods": [{"id": method_id, "name": "TRACI"}]})

    # method_id passed as product_system_id is a type mismatch
    args = {"product_system_id": method_id}
    err = validate_args("calculate_product_system", args, r)
    assert err is not None
    assert "Unknown UUID" in err["error"]


def test_registry_passes_known_uuid():
    r = UuidRegistry()
    ps_id = "eb8d30cc-1410-42c5-8dd2-8c1f82d289ec"
    method_id = "1ac50550-a158-40f3-8f31-0c5473d9f08f"
    r.track_result("list_product_systems", {"systems": [{"id": ps_id, "name": "X"}]})
    r.track_result("list_impact_methods", {"methods": [{"id": method_id, "name": "Y"}]})
    args = {"product_system_id": ps_id, "method_id": method_id}
    assert validate_args("calculate_product_system", args, r) is None


def test_registry_format_check_runs_before_lookup():
    """Malformed UUIDs should still error on format, not on registry lookup."""
    r = UuidRegistry()
    args = {"product_system_id": "not-a-uuid"}
    err = validate_args("get_product_system", args, r)
    assert err is not None
    assert "Invalid UUID format" in err["error"]