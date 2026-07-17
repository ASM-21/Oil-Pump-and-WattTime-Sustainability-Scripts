"""Module-level IPC client singleton, plus a short-TTL descriptor cache.

Per §2.2 of the design doc and script 05 verification: olca_ipc.Client recovers
automatically after IPC restart. No reset_client helper needed.
"""

import time

import olca_ipc as ipc

from config import DESCRIPTOR_CACHE_TTL_S, OLCA_PORT

_client: ipc.Client | None = None

# {descriptor_class: (cached_at_monotonic, descriptors)}. list_processes,
# list_product_systems, list_impact_methods, and ping_server all call
# get_descriptors() for their own class, and the fuzzy-match fallback added
# to list_processes makes repeated same-class calls within one turn more
# likely (an empty exact search retried with a different keyword still has
# to re-fetch the same ~tens-of-thousands-of-process catalog to search it
# again). The OpenLCA database backing this is a local desktop instance the
# user is actively working in during the same chat session, so a short TTL
# (seconds, not minutes) trades a small staleness window for materially
# fewer large IPC round trips within one exchange, without the accuracy risk
# a long-lived or permanent cache would carry.
_descriptor_cache: dict = {}


def get_client() -> ipc.Client:
    global _client
    if _client is None:
        _client = ipc.Client(OLCA_PORT)
    return _client


def get_descriptors_cached(cls, _now: float | None = None) -> list:
    """client.get_descriptors(cls), cached for DESCRIPTOR_CACHE_TTL_S.

    _now is an injection point for tests (a controlled monotonic-clock
    value) so cache-hit/expiry behavior can be verified without sleeping in
    real time; leave it None in production code.
    """
    now = _now if _now is not None else time.monotonic()
    cached = _descriptor_cache.get(cls)
    if cached is not None and (now - cached[0]) < DESCRIPTOR_CACHE_TTL_S:
        return cached[1]
    descriptors = get_client().get_descriptors(cls)
    _descriptor_cache[cls] = (now, descriptors)
    return descriptors


def clear_descriptor_cache() -> None:
    """Force the next get_descriptors_cached() call for every class to
    re-fetch. Exposed as the /refresh slash command in agent_loop.py for
    when the user knows the OpenLCA database changed mid-session."""
    _descriptor_cache.clear()
