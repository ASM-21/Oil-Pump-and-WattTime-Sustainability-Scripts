"""Unit tests for agent_loop's history truncation (§6) and the few-shot
preamble it must never drop or stub. No IPC or live model needed -- pure
list manipulation, same style as test_validation.py.

    pytest tests/test_history.py -v
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop import FEWSHOT_MESSAGES, truncate_history, _turn_starts
from config import N_MAX_TURNS, N_RECENT_TURNS


def _turn(i: int, with_tool: bool = True) -> list:
    """One synthetic user/assistant[/tool] turn, numbered for identification."""
    msgs = [{"role": "user", "content": f"question {i}"}]
    if with_tool:
        msgs.append({
            "role": "assistant", "content": "",
            "tool_calls": [{"id": f"t{i}", "function": {"name": "list_processes", "arguments": {}}}],
        })
        msgs.append({"role": "tool", "tool_call_id": f"t{i}", "content": f"result {i}"})
    msgs.append({"role": "assistant", "content": f"answer {i}", "tool_calls": []})
    return msgs


def _build_history(n_turns: int, with_tool: bool = True) -> list:
    history = [{"role": "system", "content": "sys"}]
    for i in range(n_turns):
        history.extend(_turn(i, with_tool))
    return history


def _tool_messages(history: list) -> list:
    return [m for m in history if m.get("role") == "tool"]


# ---------- _turn_starts ----------

def test_turn_starts_finds_all_user_messages():
    history = _build_history(3)
    starts = _turn_starts(history)
    user_indices = [i for i, m in enumerate(history) if m.get("role") == "user"]
    assert starts == user_indices + [len(history)]


def test_turn_starts_respects_start_at():
    history = _build_history(3)
    first_user = next(i for i, m in enumerate(history) if m.get("role") == "user")
    starts = _turn_starts(history, start_at=first_user + 1)
    assert first_user not in starts[:-1], "start_at should exclude the first turn's user message"


# ---------- truncate_history: original behavior (preserve_prefix_len=0) ----------

def test_short_history_untouched():
    history = _build_history(N_RECENT_TURNS)  # exactly at the "keep in full" boundary
    before = json.dumps(history)
    result = truncate_history(history)
    assert result is history, "should return the same list object"
    assert json.dumps(history) == before, "short history must not be mutated at all"


def test_old_turns_dropped_past_n_max_turns():
    n_turns = N_MAX_TURNS + 2
    history = _build_history(n_turns, with_tool=False)
    truncate_history(history)
    remaining_turns = len([m for m in history if m.get("role") == "user"])
    assert remaining_turns == N_MAX_TURNS, (
        f"expected exactly {N_MAX_TURNS} turns to survive, got {remaining_turns}"
    )
    # The oldest surviving turn should be turn index (n_turns - N_MAX_TURNS),
    # not turn 0 -- confirms the *oldest* turns were the ones dropped.
    first_user_content = next(m["content"] for m in history if m.get("role") == "user")
    assert first_user_content == f"question {n_turns - N_MAX_TURNS}"


def test_system_message_always_kept():
    history = _build_history(N_MAX_TURNS + 3)
    truncate_history(history)
    assert history[0] == {"role": "system", "content": "sys"}


def test_tool_messages_stubbed_between_recent_and_max():
    # n_turns between N_RECENT_TURNS and N_MAX_TURNS: no turns dropped, but
    # the tool messages in turns older than N_RECENT_TURNS get stubbed.
    n_turns = N_RECENT_TURNS + 2
    assert n_turns <= N_MAX_TURNS, "test assumption: fits without triggering the drop path"
    history = _build_history(n_turns)
    truncate_history(history)
    tool_msgs = _tool_messages(history)
    assert len(tool_msgs) == n_turns, "no turns should have been dropped"
    stubbed = [m for m in tool_msgs if m.get("_summarized")]
    unstubbed = [m for m in tool_msgs if not m.get("_summarized")]
    assert len(stubbed) == n_turns - N_RECENT_TURNS
    assert len(unstubbed) == N_RECENT_TURNS
    for m in stubbed:
        payload = json.loads(m["content"])
        assert payload["_summarized"] is True
        assert "preview" in payload


# ---------- truncate_history: few-shot preamble preservation ----------

def test_fewshot_preamble_never_dropped_or_stubbed():
    """The whole point of preserve_prefix_len: no matter how long the real
    conversation grows, the few-shot example must survive intact."""
    history = [{"role": "system", "content": "sys"}]
    history.extend(FEWSHOT_MESSAGES)
    n_turns = N_MAX_TURNS + 5  # well past the drop threshold
    for i in range(n_turns):
        history.extend(_turn(i))

    original_fewshot = json.dumps(FEWSHOT_MESSAGES)
    truncate_history(history, preserve_prefix_len=len(FEWSHOT_MESSAGES))

    preamble = history[1:1 + len(FEWSHOT_MESSAGES)]
    assert json.dumps(preamble) == original_fewshot, (
        "few-shot preamble must survive byte-for-byte even after heavy truncation"
    )
    # And real turns still get truncated per the normal rules, past the preamble.
    real_turns = [m for m in history[1 + len(FEWSHOT_MESSAGES):] if m.get("role") == "user"]
    assert len(real_turns) == N_MAX_TURNS


def test_fewshot_preamble_not_counted_as_a_real_turn():
    """The few-shot preamble's own 'user' message must not consume one of
    the N_RECENT_TURNS/N_MAX_TURNS slots meant for the real conversation."""
    history = [{"role": "system", "content": "sys"}]
    history.extend(FEWSHOT_MESSAGES)
    # Exactly N_MAX_TURNS real turns: if the preamble were miscounted as an
    # extra turn, this would incorrectly trigger the drop path.
    for i in range(N_MAX_TURNS):
        history.extend(_turn(i))

    truncate_history(history, preserve_prefix_len=len(FEWSHOT_MESSAGES))
    real_turns = [m for m in history[1 + len(FEWSHOT_MESSAGES):] if m.get("role") == "user"]
    assert len(real_turns) == N_MAX_TURNS, (
        "all real turns should survive; the preamble must not eat into the turn budget"
    )


def test_reproduces_original_behavior_when_preserve_prefix_len_zero():
    """preserve_prefix_len defaults to 0 and must reproduce the exact
    original (pre-few-shot) truncation behavior for any caller that doesn't
    pass it -- regression guard for the generalization."""
    n_turns = N_MAX_TURNS + 3
    h1 = _build_history(n_turns)
    h2 = _build_history(n_turns)
    truncate_history(h1)  # old call shape
    truncate_history(h2, preserve_prefix_len=0)  # explicit default
    assert json.dumps(h1) == json.dumps(h2)


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
