"""Inventory tools."""

import difflib
import re

from requests.exceptions import ConnectionError

import olca_schema as o
from ipc_client import get_client
from config import FUZZY_TOKEN_MATCH, FUZZY_TOKEN_SCORE, MAX_DESCRIPTORS, MAX_FLOWS

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _all_amounts_none(items: list, field: str = "amount") -> bool:
    if not items:
        return False
    return all(item.get(field) is None for item in items)


def _tokens(text: str) -> list:
    return _TOKEN_RE.findall((text or "").lower())


def _token_overlap_score(query_tokens: list, name: str) -> float:
    """Fraction of query_tokens that fuzzy-match some word in `name`.

    Plain difflib.get_close_matches() over WHOLE process names was tried
    first and rejected: LCA database names are long, structured, comma-
    qualified strings ("aluminium ingot, primary, at plant" vs "aluminium
    sheet rolling"), and whole-string SequenceMatcher.ratio() is dominated
    by overall length/composition, not by whether the meaningful words
    match. Empirically, querying "aluminum ingot" against a small sample
    scored the WRONG process ("aluminium sheet rolling", ratio 0.649) above
    the right one ("aluminium ingot, primary, at plant", ratio 0.583).
    Per-token matching (does each query word have a close match somewhere
    in the name) doesn't have that failure mode and is the standard fix for
    fuzzy-matching structured/qualified names.
    """
    name_tokens = _tokens(name)
    if not query_tokens or not name_tokens:
        return 0.0
    matched = 0
    for qt in query_tokens:
        if any(qt == nt or qt in nt or nt in qt for nt in name_tokens):
            matched += 1
            continue
        best = max(
            (difflib.SequenceMatcher(None, qt, nt).ratio() for nt in name_tokens),
            default=0.0,
        )
        if best >= FUZZY_TOKEN_MATCH:
            matched += 1
    return matched / len(query_tokens)


def _search_processes(descriptors: list, keyword: str) -> tuple[list, bool]:
    """Case-insensitive substring match on process name; if that finds
    nothing, fall back to a per-token fuzzy match over all names (see
    _token_overlap_score for why token-level, not whole-string, matching).

    LCA database naming is inconsistent in exactly the ways that break exact
    substring search: regional spelling ("aluminum" vs "aluminium"),
    qualifier order ("aluminium ingot, primary" vs "primary aluminium
    ingot"), abbreviations. A local model asked to find a process from a
    natural-language description will often guess a keyword that is close
    but not a substring; returning zero results in that case forces several
    wasted tool-call round trips (and risks hitting MAX_TOOL_ITERATIONS)
    before the model tries a lucky exact phrase. Falling back to fuzzy
    matching turns that into one call. Returns (matches, was_fuzzy), ranked
    best-score-first when fuzzy.
    """
    kw = (keyword or "").lower().strip()
    if not kw:
        return list(descriptors), False

    exact = [d for d in descriptors if kw in (d.name or "").lower()]
    if exact:
        return exact, False

    query_tokens = _tokens(kw)
    scored = [(d, _token_overlap_score(query_tokens, d.name or "")) for d in descriptors]
    scored = [(d, s) for d, s in scored if s >= FUZZY_TOKEN_SCORE]
    if not scored:
        return [], False
    scored.sort(key=lambda ds: ds[1], reverse=True)
    return [d for d, _ in scored], True


def list_processes(keyword: str = "") -> dict:
    """Search processes by name. Capped at MAX_DESCRIPTORS.

    Tries a case-insensitive substring match first. If that finds nothing,
    falls back to a fuzzy (edit-distance) match over all process names --
    check the `fuzzy_match` field in the result: when true, these are
    approximate matches, not confirmed exact hits, and should be presented
    to the user as candidates ("did you mean...") rather than treated as
    the one correct process.

    Args: keyword (required - empty string returns the first 50 of 25k+ processes).
    Returns: {processes: [{id, name}, ...], returned, total_matching,
    total_in_db, fuzzy_match}
    """
    try:
        client = get_client()
        descriptors = client.get_descriptors(o.Process)
        filtered, fuzzy = _search_processes(descriptors, keyword)
        out = [{"id": d.id, "name": d.name} for d in filtered[:MAX_DESCRIPTORS]]
        return {
            "processes": out,
            "returned": len(out),
            "total_matching": len(filtered),
            "total_in_db": len(descriptors),
            "fuzzy_match": fuzzy,
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