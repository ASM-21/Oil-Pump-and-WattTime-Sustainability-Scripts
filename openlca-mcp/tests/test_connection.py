"""Smoke test. Run with OpenLCA + IPC up:

    python tests/test_connection.py

Expected output: "Connected. Found N product systems."
"""

import sys
from pathlib import Path

# Allow running from project root or tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import olca_schema as o
from ipc_client import get_client


def main() -> int:
    try:
        client = get_client()
        systems = client.get_descriptors(o.ProductSystem)
        print(f"Connected. Found {len(systems)} product systems.")
        return 0
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
