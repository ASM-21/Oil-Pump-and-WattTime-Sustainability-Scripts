"""Unit tests for ipc_client's short-TTL descriptor cache. No real IPC
needed -- get_client() is monkeypatched to a fake with a call counter, and
the cache's clock is injected via the _now parameter so TTL behavior can be
tested without sleeping in real time.

    pytest tests/test_ipc_cache.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ipc_client
from config import DESCRIPTOR_CACHE_TTL_S


class _FakeClient:
    def __init__(self):
        self.calls = []

    def get_descriptors(self, cls):
        self.calls.append(cls)
        return [f"{cls.__name__}-descriptor"]


class _FakeCls:
    """Stand-in for an olca_schema class, used only as a cache dict key."""


def _reset(monkeypatch_client):
    ipc_client._client = monkeypatch_client
    ipc_client._descriptor_cache.clear()


def test_first_call_hits_the_real_client():
    fake = _FakeClient()
    _reset(fake)
    ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    assert len(fake.calls) == 1


def test_second_call_within_ttl_is_a_cache_hit():
    fake = _FakeClient()
    _reset(fake)
    ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    ipc_client.get_descriptors_cached(_FakeCls, _now=DESCRIPTOR_CACHE_TTL_S - 1)
    assert len(fake.calls) == 1, "should have served the cached value, not refetched"


def test_call_after_ttl_expires_refetches():
    fake = _FakeClient()
    _reset(fake)
    ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    ipc_client.get_descriptors_cached(_FakeCls, _now=DESCRIPTOR_CACHE_TTL_S + 1)
    assert len(fake.calls) == 2, "expired entry should trigger a real refetch"


def test_cache_is_per_class():
    fake = _FakeClient()
    _reset(fake)

    class _OtherCls:
        __name__ = "OtherEntity"

    ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    ipc_client.get_descriptors_cached(_OtherCls, _now=0.0)
    assert len(fake.calls) == 2, "different classes must not share a cache slot"
    # both still hit cache on a second call within TTL
    ipc_client.get_descriptors_cached(_FakeCls, _now=1.0)
    ipc_client.get_descriptors_cached(_OtherCls, _now=1.0)
    assert len(fake.calls) == 2


def test_clear_descriptor_cache_forces_refetch():
    fake = _FakeClient()
    _reset(fake)
    ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    ipc_client.clear_descriptor_cache()
    ipc_client.get_descriptors_cached(_FakeCls, _now=0.1)  # well within TTL, but cache was cleared
    assert len(fake.calls) == 2


def test_returned_value_matches_underlying_client():
    fake = _FakeClient()
    _reset(fake)
    result = ipc_client.get_descriptors_cached(_FakeCls, _now=0.0)
    # NOTE: _FakeCls.__name__ resolves to the real class name ("_FakeCls"),
    # not the "FakeEntity" string assigned in the class body -- type.__name__
    # is a data descriptor on the metaclass and wins over a same-named class
    # attribute. Assert against the real name, not the unrelated class-body
    # assignment.
    assert result == [f"{_FakeCls.__name__}-descriptor"]


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed, failed = 0, []
    for fn in fns:
        try:
            fn()
            passed += 1
        except Exception as e:
            failed.append((fn.__name__, e))
    print(f"{passed} passed, {len(failed)} failed")
    for name, e in failed:
        print(f" FAIL {name}: {e}")
        traceback.print_exception(type(e), e, e.__traceback__)
