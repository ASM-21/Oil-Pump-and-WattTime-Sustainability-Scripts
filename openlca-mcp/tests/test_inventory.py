"""Unit tests for list_processes' fuzzy-matching fallback. No IPC required
-- these exercise pure functions with fake descriptor objects, same style as
test_validation.py.

    pytest tests/test_inventory.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.inventory import _search_processes, _token_overlap_score, _tokens


class _FakeDescriptor:
    """Minimal stand-in for olca_schema's Process descriptor: just id/name."""
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


DESCRIPTORS = [
    _FakeDescriptor("1", "aluminium ingot, primary, at plant"),
    _FakeDescriptor("2", "transport, freight, lorry"),
    _FakeDescriptor("3", "electricity, medium voltage"),
    _FakeDescriptor("4", "aluminium sheet rolling"),
    _FakeDescriptor("5", "steel ingot, primary, at plant"),
]


# ---------- Exact substring search still wins when it finds anything ----------

def test_exact_substring_match_no_fuzzy_flag():
    matches, fuzzy = _search_processes(DESCRIPTORS, "aluminium")
    assert fuzzy is False
    assert {d.name for d in matches} == {
        "aluminium ingot, primary, at plant", "aluminium sheet rolling"
    }


def test_exact_substring_beats_fuzzy_even_if_similar_names_exist():
    """steel/aluminium ingots are similar strings; an exact hit on one must
    not accidentally pull in the other."""
    matches, fuzzy = _search_processes(DESCRIPTORS, "steel ingot")
    assert fuzzy is False
    assert len(matches) == 1
    assert matches[0].name == "steel ingot, primary, at plant"


def test_empty_keyword_returns_everything_not_fuzzy():
    matches, fuzzy = _search_processes(DESCRIPTORS, "")
    assert fuzzy is False
    assert len(matches) == len(DESCRIPTORS)


# ---------- Fuzzy fallback: the reason this file exists ----------

def test_fuzzy_fallback_on_regional_spelling_mismatch():
    """'aluminum' (US) has zero exact hits against 'aluminium' (UK/database
    spelling); the fallback must find the right process anyway."""
    matches, fuzzy = _search_processes(DESCRIPTORS, "aluminum ingot")
    assert fuzzy is True
    assert len(matches) >= 1
    assert matches[0].name == "aluminium ingot, primary, at plant", (
        "the fuzzy match must rank the actually-relevant process first; "
        f"got {[d.name for d in matches]}"
    )


def test_fuzzy_fallback_does_not_fire_on_unrelated_keyword():
    """A keyword sharing no real similarity with anything in the database
    should come back empty, not fuzzy-matched to something irrelevant."""
    matches, fuzzy = _search_processes(DESCRIPTORS, "zzzzzzzzzz_not_a_real_thing")
    assert matches == []
    assert fuzzy is False


def test_token_overlap_score_prefers_whole_word_match_over_short_string():
    """Regression guard for the failure mode that motivated token-level
    matching in the first place: plain difflib.get_close_matches() over
    WHOLE process names scored 'aluminium sheet rolling' (0.649) above the
    actually-relevant 'aluminium ingot, primary, at plant' (0.583) for the
    query 'aluminum ingot', because whole-string ratio is dominated by
    overall length/composition on these long, comma-qualified LCA names.
    Token-level scoring must not repeat that."""
    tokens = _tokens("aluminum ingot")
    score_right = _token_overlap_score(tokens, "aluminium ingot, primary, at plant")
    score_wrong = _token_overlap_score(tokens, "aluminium sheet rolling")
    assert score_right > score_wrong, (
        f"expected the ingot process to score higher: right={score_right} "
        f"wrong={score_wrong}"
    )


if __name__ == "__main__":
    # Allow `python tests/test_inventory.py` without pytest, matching how
    # test_validation.py's functions can be run directly.
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
