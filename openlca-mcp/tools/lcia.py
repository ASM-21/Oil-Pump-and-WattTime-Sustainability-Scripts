"""LCIA tools.

Lifecycle (verified by script 04):
  setup -> calculate -> wait_until_ready -> fetch -> dispose

Silent-failure guard:
  Contributions and grouped results have shape access paths that are best-guesses
  from olca-ipc 2.4 method names (§14 open risk). If our access path is wrong,
  every entry returns {amount: None, ...}. We detect this and return an error
  instead of letting the agent get fooled by all-null results.
"""

from requests.exceptions import ConnectionError

import olca_schema as o
from ipc_client import get_client, get_descriptors_cached
from config import MAX_CONTRIBUTIONS


def _make_setup(product_system_id: str, method_id: str) -> o.CalculationSetup:
    return o.CalculationSetup(
        target=o.Ref(ref_type=o.RefType.ProductSystem, id=product_system_id),
        impact_method=o.Ref(ref_type=o.RefType.ImpactMethod, id=method_id),
        amount=1.0,
    )


def _all_amounts_none(items: list, field: str = "amount") -> bool:
    """True if every item has None in `field`. Indicates a shape-access bug."""
    if not items:
        return False  # empty is legitimate, not a failure
    return all(item.get(field) is None for item in items)


def _all_none(items: list, *fields: str) -> bool:
    """True if every item has None in ALL of `fields`. Stricter than
    _all_amounts_none: catches a shape bug that only breaks identity fields
    (e.g. process/process_id) while amount still comes through fine, which
    _all_amounts_none alone would miss."""
    if not items:
        return False
    return all(all(item.get(f) is None for f in fields) for item in items)


def list_impact_methods() -> dict:
    """List all LCIA methods. REQUIRED before any calculation that needs a method_id.

    Returns: {methods: [{id, name, description}, ...], count}
    """
    try:
        descriptors = get_descriptors_cached(o.ImpactMethod)
        out = [
            {
                "id": d.id,
                "name": d.name,
                "description": getattr(d, "description", None),
            }
            for d in descriptors
        ]
        return {"methods": out, "count": len(out)}
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def calculate_product_system(product_system_id: str, method_id: str) -> dict:
    """Run LCIA. REQUIRED before stating any impact value or category result.

    Args: product_system_id, method_id (both UUIDs from listing tools).
    Returns: {impacts: [{category, category_id, amount, unit}, ...], count}.
    Functional unit count is 1.0. Returns ALL categories - do not call twice for same inputs.
    """
    client = get_client()
    setup = _make_setup(product_system_id, method_id)

    result = None
    try:
        result = client.calculate(setup)
        result.wait_until_ready()
        impacts = result.get_total_impacts()
        out = [
            {
                "category": iv.impact_category.name,
                "category_id": iv.impact_category.id,
                "amount": iv.amount,
                "unit": iv.impact_category.ref_unit,
            }
            for iv in impacts
        ]
        return {"impacts": out, "count": len(out)}
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        if result is not None:
            try:
                result.dispose()
            except Exception:
                pass


def get_impact_contributions(
    product_system_id: str,
    method_id: str,
    impact_category_id: str,
) -> dict:
    """Per-process contribution to one impact category.

    Args: product_system_id, method_id, impact_category_id (the last from a prior
    calculate_product_system result).
    Returns: {contributions: [{process, process_id, amount, share}, ...], total_returned, total_available}
    Top results by absolute amount, capped at MAX_CONTRIBUTIONS.
    """
    client = get_client()
    setup = _make_setup(product_system_id, method_id)
    category_ref = o.Ref(ref_type=o.RefType.ImpactCategory, id=impact_category_id)

    result = None
    try:
        result = client.calculate(setup)
        result.wait_until_ready()
        contribs = result.get_impact_contributions_of(category_ref)
        sorted_contribs = sorted(
            contribs, key=lambda c: abs(getattr(c, "amount", 0.0) or 0.0), reverse=True
        )
        out = []
        for c in sorted_contribs[:MAX_CONTRIBUTIONS]:
            # olca_schema.ContributionItem exposes the contributing entity as
            # `item` (a Ref with .id/.name directly), not `tech_flow.provider`
            # -- confirmed against the published ContributionItem field list
            # (item: Ref, amount: float, share: float, rest: bool, unit: str).
            # The old `tech_flow`/`provider` access was the "best-guess" this
            # module's own §14 note warned about: it silently produced
            # process="unknown"/process_id=None for every row while `amount`
            # (a top-level field) still came through fine, so the old
            # _all_amounts_none guard never caught it. Falling back to the old
            # path defensively in case an older olca-ipc build differs.
            item = getattr(c, "item", None) or getattr(
                getattr(c, "tech_flow", None), "provider", None
            )
            out.append(
                {
                    "process": getattr(item, "name", "unknown") if item else "unknown",
                    "process_id": getattr(item, "id", None) if item else None,
                    "amount": getattr(c, "amount", None),
                    "share": getattr(c, "share", None),
                }
            )
        # Silent-failure guard: catches a bad access path whether it breaks
        # `amount` alone, `process`/`process_id` alone (the bug this exact
        # guard used to miss), or all of them.
        if _all_amounts_none(out) or _all_none(out, "process_id"):
            return {
                "error": (
                    "All contribution amounts or process IDs came back as None. "
                    "The shape access path in get_impact_contributions is likely "
                    "wrong (see §14). Check tools/lcia.py and probe the real "
                    "entry shape with print(repr(contribs[0]))."
                ),
                "total_available": len(contribs),
            }
        return {
            "contributions": out,
            "total_returned": len(out),
            "total_available": len(contribs),
        }
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        if result is not None:
            try:
                result.dispose()
            except Exception:
                pass


def get_grouped_impact_results(
    product_system_id: str,
    method_id: str,
    impact_category_id: str,
) -> dict:
    """Pareto view of contributions grouped by process group.

    Args: product_system_id, method_id, impact_category_id.
    Returns: {groups: [{group, amount}, ...], count} ordered by absolute amount descending.
    """
    client = get_client()
    setup = _make_setup(product_system_id, method_id)
    category_ref = o.Ref(ref_type=o.RefType.ImpactCategory, id=impact_category_id)

    result = None
    try:
        result = client.calculate(setup)
        result.wait_until_ready()
        groups = result.get_grouped_impact_results_of(category_ref)
        out = [
            {
                "group": getattr(g, "name", None) or getattr(g, "group", "ungrouped"),
                "amount": getattr(g, "amount", None),
            }
            for g in groups
        ]
        out.sort(key=lambda r: abs(r["amount"] or 0.0), reverse=True)
        if _all_amounts_none(out):
            return {
                "error": (
                    "All group amounts came back as None. The shape access "
                    "path in get_grouped_impact_results is likely wrong (see §14). "
                    "Check tools/lcia.py."
                ),
                "total_available": len(groups),
            }
        return {"groups": out, "count": len(out)}
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        if result is not None:
            try:
                result.dispose()
            except Exception:
                pass