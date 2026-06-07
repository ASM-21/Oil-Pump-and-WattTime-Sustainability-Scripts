"""Inventory tools."""

from requests.exceptions import ConnectionError

import olca_schema as o
from ipc_client import get_client
from config import MAX_DESCRIPTORS, MAX_FLOWS


def _all_amounts_none(items: list, field: str = "amount") -> bool:
    if not items:
        return False
    return all(item.get(field) is None for item in items)


def list_processes(keyword: str = "") -> dict:
    """Search processes by case-insensitive substring on name. Capped at MAX_DESCRIPTORS.

    Args: keyword (required - empty string returns the first 50 of 25k+ processes).
    Returns: {processes: [{id, name}, ...], returned, total_matching, total_in_db}
    """
    try:
        client = get_client()
        descriptors = client.get_descriptors(o.Process)
        kw = (keyword or "").lower().strip()
        if kw:
            filtered = [d for d in descriptors if kw in (d.name or "").lower()]
        else:
            filtered = list(descriptors)
        out = [{"id": d.id, "name": d.name} for d in filtered[:MAX_DESCRIPTORS]]
        return {
            "processes": out,
            "returned": len(out),
            "total_matching": len(filtered),
            "total_in_db": len(descriptors),
        }
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def get_process_info(id: str) -> dict:
    """Inputs and outputs for one process.

    Args: id (UUID from list_processes).
    Returns: dict with name, description, category, inputs/outputs lists, counts.
    """
    try:
        client = get_client()
        proc = client.get(o.Process, id)
        if proc is None:
            return {"error": f"No process with id {id}"}

        inputs, outputs = [], []
        for ex in (proc.exchanges or []):
            entry = {
                "flow": getattr(ex.flow, "name", None) if ex.flow else None,
                "flow_id": getattr(ex.flow, "id", None) if ex.flow else None,
                "amount": ex.amount,
                "unit": getattr(ex.unit, "name", None) if ex.unit else None,
                "is_quantitative_reference": bool(getattr(ex, "is_quantitative_reference", False)),
            }
            if getattr(ex, "is_input", False):
                inputs.append(entry)
            else:
                outputs.append(entry)

        return {
            "id": proc.id,
            "name": proc.name,
            "description": proc.description,
            "category": getattr(proc, "category", None),
            "inputs": inputs,
            "outputs": outputs,
            "input_count": len(inputs),
            "output_count": len(outputs),
        }
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def get_total_flows(product_system_id: str, method_id: str) -> dict:
    """Top inventory flows by absolute amount for a calculated product system.

    Args: product_system_id, method_id (both required even though flows are LCI -
    the lifecycle pattern is shared with LCIA tools).
    Returns: {flows: [{flow, flow_id, amount, unit, is_input}, ...], total_returned, total_available}
    """
    client = get_client()
    setup = o.CalculationSetup(
        target=o.Ref(ref_type=o.RefType.ProductSystem, id=product_system_id),
        impact_method=o.Ref(ref_type=o.RefType.ImpactMethod, id=method_id),
        amount=1.0,
    )

    result = None
    try:
        result = client.calculate(setup)
        result.wait_until_ready()
        flows = result.get_total_flows()
        sorted_flows = sorted(
            flows, key=lambda f: abs(getattr(f, "amount", 0.0) or 0.0), reverse=True
        )
        out = []
        for f in sorted_flows[:MAX_FLOWS]:
            envi = getattr(f, "envi_flow", None)
            flow_ref = getattr(envi, "flow", None) if envi else None
            out.append(
                {
                    "flow": getattr(flow_ref, "name", None),
                    "flow_id": getattr(flow_ref, "id", None),
                    "amount": getattr(f, "amount", None),
                    "unit": getattr(flow_ref, "ref_unit", None),
                    "is_input": getattr(envi, "is_input", None) if envi else None,
                }
            )
        if _all_amounts_none(out):
            return {
                "error": (
                    "All flow amounts came back as None. The EnviFlowValue access "
                    "path in get_total_flows is likely wrong (see §14). "
                    "Check tools/inventory.py."
                ),
                "total_available": len(flows),
            }
        return {
            "flows": out,
            "total_returned": len(out),
            "total_available": len(flows),
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