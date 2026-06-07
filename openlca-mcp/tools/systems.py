"""Product system tools."""

from requests.exceptions import ConnectionError

import olca_schema as o
from ipc_client import get_client


def list_product_systems() -> dict:
    """List all product systems. REQUIRED before any calculation that needs a product_system_id.

    Returns: {systems: [{id, name, description}, ...], count}
    """
    try:
        client = get_client()
        descriptors = client.get_descriptors(o.ProductSystem)
        out = [
            {
                "id": d.id,
                "name": d.name,
                "description": getattr(d, "description", None),
            }
            for d in descriptors
        ]
        return {"systems": out, "count": len(out)}
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def get_product_system(id: str) -> dict:
    """Full details for one product system.

    Args: id (UUID from list_product_systems).
    Returns: dict with name, description, reference flow, target amount/unit.
    """
    try:
        client = get_client()
        ps = client.get(o.ProductSystem, id)
        if ps is None:
            return {"error": f"No product system with id {id}"}
        data = ps.to_dict() if hasattr(ps, "to_dict") else dict(ps.__dict__)
        # Trim the heaviest fields for the LLM context
        for heavy in ("processes", "process_links", "parameter_sets"):
            if heavy in data and isinstance(data[heavy], list):
                data[f"{heavy}_count"] = len(data[heavy])
                data.pop(heavy)
        return data
    except ConnectionError:
        return {"error": "OpenLCA IPC unreachable on port 8081."}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}