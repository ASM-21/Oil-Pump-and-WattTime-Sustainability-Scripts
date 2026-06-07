"""Module-level IPC client singleton.

Per §2.2 of the design doc and script 05 verification: olca_ipc.Client recovers
automatically after IPC restart. No reset_client helper needed.
"""

import olca_ipc as ipc

from config import OLCA_PORT

_client: ipc.Client | None = None


def get_client() -> ipc.Client:
    global _client
    if _client is None:
        _client = ipc.Client(OLCA_PORT)
    return _client
