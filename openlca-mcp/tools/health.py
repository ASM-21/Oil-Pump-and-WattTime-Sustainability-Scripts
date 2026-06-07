"""Health check tool."""

from requests.exceptions import ConnectionError

import olca_schema as o
from ipc_client import get_client


def ping_server() -> dict:
    """Check OpenLCA IPC reachability. Returns {ok: bool, product_system_count?: int, error?: str}."""
    try:
        client = get_client()
        descriptors = client.get_descriptors(o.ProductSystem)
        return {"ok": True, "product_system_count": len(descriptors)}
    except ConnectionError:
        return {
            "ok": False,
            "error": "OpenLCA IPC unreachable on port 8081. Is OpenLCA open with the IPC server started?",
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}