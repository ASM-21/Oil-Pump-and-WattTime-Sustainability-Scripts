"""Pre-dispatch arg validation.

Three layers:

1. UUID_RE catches malformed UUIDs (wrong length, non-hex chars).
2. UuidRegistry catches invented-but-syntactically-valid UUIDs by tracking
   what the listing/calc tools have actually returned this session, with
   per-type buckets so a flow_id can't be passed as a process_id.
3. validate_against_schema (optional, needs the tool's JSON inputSchema)
   catches missing required fields and grossly wrong types before the call
   ever reaches olca-ipc, where a TypeError/KeyError would otherwise
   surface as an unhelpful raw Python exception the model can't act on.

The model has been observed inventing UUIDs that pass the regex but don't
exist in the database. The registry is the only thing that catches those.

Local tool-calling models (this project targets qwen3:8b via Ollama) are
also documented to not reliably follow the tool-call protocol: Qwen's own
function-calling guidance is explicit that "it is not guaranteed that the
model generation will always follow the protocol... be prepared that if it
breaks, countermeasures are in place" (qwen.readthedocs.io, function_call
docs). One specific, currently-open failure mode across multiple
Ollama-based tool-calling stacks (see e.g. ollama/ollama and downstream
proxy issues from 2025-2026) is that `arguments` sometimes arrives as a
JSON-encoded STRING instead of an already-parsed object. coerce_tool_args()
below repairs that case instead of failing on it.
"""

import json
import re

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Per-field expected source. The agent loop validates UUID-shaped args against
# the corresponding bucket in the registry.
UUID_FIELDS = {
    "product_system_id": "list_product_systems",
    "method_id": "list_impact_methods",
    "impact_category_id": "calculate_product_system",
    "process_id": "list_processes",
    "id": None,  # context-dependent; checked against the global "all" bucket
}


class UuidRegistry:
    """Tracks UUIDs returned by listing and discovery tools.

    Per-bucket so we can reject a UUID passed in the wrong field (e.g.,
    impact_category_id sent in a product_system_id slot).
    """

    def __init__(self) -> None:
        self.product_systems: set[str] = set()
        self.methods: set[str] = set()
        self.categories: set[str] = set()
        self.processes: set[str] = set()
        # Union of everything we've ever seen, for the generic `id` field.
        self.all: set[str] = set()

    def clear(self) -> None:
        for bucket in (
            self.product_systems,
            self.methods,
            self.categories,
            self.processes,
            self.all,
        ):
            bucket.clear()

    def track_result(self, tool_name: str, result: dict) -> None:
        """Add UUIDs from a tool result to the right bucket(s).

        Only inspects the listing/discovery tools that are the legitimate
        source of UUIDs. Contribution and flow tools also contain UUIDs but
        those aren't the entry points for type-aware lookup.
        """
        if not isinstance(result, dict):
            return

        if tool_name == "list_product_systems":
            for s in result.get("systems", []) or []:
                self._add(self.product_systems, s.get("id"))
        elif tool_name == "list_impact_methods":
            for m in result.get("methods", []) or []:
                self._add(self.methods, m.get("id"))
        elif tool_name == "list_processes":
            for p in result.get("processes", []) or []:
                self._add(self.processes, p.get("id"))
        elif tool_name == "calculate_product_system":
            # category_id is the only place these UUIDs surface
            for i in result.get("impacts", []) or []:
                self._add(self.categories, i.get("category_id"))
        elif tool_name == "get_product_system":
            self._add(self.product_systems, result.get("id"))
        elif tool_name == "get_process_info":
            self._add(self.processes, result.get("id"))
        # No-op for ping_server, get_impact_contributions, etc.

    def _add(self, bucket: set[str], val) -> None:
        if isinstance(val, str) and UUID_RE.match(val):
            normalized = val.lower()
            bucket.add(normalized)
            self.all.add(normalized)

    def is_known_for(self, field: str, uuid: str) -> bool:
        u = uuid.lower()
        if field == "product_system_id":
            return u in self.product_systems
        if field == "method_id":
            return u in self.methods
        if field == "impact_category_id":
            return u in self.categories
        if field == "process_id":
            return u in self.processes
        if field == "id":
            return u in self.all
        return True  # unknown field, don't block


def validate_args(
    fn_name: str,
    args: dict,
    registry: UuidRegistry | None = None,
) -> dict | None:
    """Return None if args are valid, else an error dict ready to send back.

    Two-layer check on UUID-shaped fields:
    1. Format must match UUID_RE.
    2. If a registry is supplied, the value must exist in the right bucket.
    """
    if not isinstance(args, dict):
        return {
            "error": f"Tool {fn_name} expected dict args, got {type(args).__name__}."
        }

    for key, val in args.items():
        if key not in UUID_FIELDS:
            continue
        if val is None or val == "":
            continue
        s = str(val)
        source = UUID_FIELDS[key] or "the appropriate listing tool"

        if not UUID_RE.match(s):
            return {
                "error": (
                    f"Invalid UUID format for '{key}': '{val}'. "
                    f"Call {source} first to get a real ID. Do not invent UUIDs."
                )
            }

        if registry is not None and not registry.is_known_for(key, s):
            return {
                "error": (
                    f"Unknown UUID for '{key}': '{val}'. "
                    f"This UUID was not returned by any tool in this conversation. "
                    f"Call {source} first to get a real ID. Do not invent UUIDs."
                )
            }
    return None


def coerce_tool_args(raw_args, fn_name: str = "") -> tuple[dict | None, dict | None]:
    """Normalize a tool call's raw arguments into a dict, repairing the
    known Ollama failure mode where `arguments` arrives as a JSON-encoded
    string rather than an already-parsed object (observed across several
    Ollama-based tool-calling stacks in 2025-2026, not specific to this
    project). Returns (args_dict, None) on success, or (None, error_dict)
    if raw_args is neither a dict nor a JSON object string.
    """
    if isinstance(raw_args, dict):
        return raw_args, None
    if raw_args is None:
        return {}, None
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError as e:
            return None, {
                "error": (
                    f"Tool {fn_name} arguments could not be parsed as JSON "
                    f"({e}). Arguments must be a single JSON object, e.g. "
                    '{"key": "value"}. Re-issue the tool call with valid '
                    "JSON object arguments."
                )
            }
        if isinstance(parsed, dict):
            return parsed, None
        return None, {
            "error": (
                f"Tool {fn_name} arguments parsed to a "
                f"{type(parsed).__name__}, not a JSON object. Arguments must "
                'be a single JSON object, e.g. {"key": "value"}.'
            )
        }
    return None, {
        "error": f"Tool {fn_name} arguments must be a JSON object; got "
                 f"{type(raw_args).__name__}."
    }


# JSON Schema "type" -> acceptable Python types. bool is deliberately not
# accepted for "integer"/"number": in Python bool is an int subclass, but a
# model passing true/false where a count or amount is expected is a real
# type error, not a technicality.
_SCHEMA_TYPE_MAP = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def _type_ok(value, schema_type) -> bool:
    types = [schema_type] if isinstance(schema_type, str) else list(schema_type or [])
    if not types:
        return True  # no declared type -- nothing to check
    if value is None and "null" in types:
        return True
    for t in types:
        py_types = _SCHEMA_TYPE_MAP.get(t)
        if py_types is None:
            continue  # unknown/unsupported schema type keyword -- don't block
        if t in ("integer", "number") and isinstance(value, bool):
            continue  # bool is an int subclass; explicitly excluded above
        if isinstance(value, py_types):
            return True
    return False


def validate_against_schema(fn_name: str, args: dict, schema: dict | None) -> dict | None:
    """Structural check of `args` against a tool's JSON inputSchema, before
    the call ever reaches olca-ipc.

    Deliberately minimal (no external jsonschema dependency, matching this
    project's requirements.txt): checks that every schema-required property
    is present and non-null, and that present properties whose schema
    declares a "type" roughly match it. Does not attempt full JSON Schema
    semantics (patterns, enums, nested object/array validation, additional
    properties) -- those failures still reach olca-ipc and surface as a
    normal tool error, just without this earlier, more actionable message.

    Returns None if schema is falsy (no schema available -- nothing to
    check) or args pass; otherwise an error dict.
    """
    if not schema or not isinstance(schema, dict):
        return None
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    missing = [r for r in required if r not in args or args.get(r) is None]
    if missing:
        return {
            "error": (
                f"Tool {fn_name} is missing required argument(s): "
                f"{', '.join(missing)}. Provide all required arguments."
            )
        }

    for key, val in args.items():
        prop_schema = properties.get(key)
        if not isinstance(prop_schema, dict):
            continue  # unknown property; let the tool itself decide
        schema_type = prop_schema.get("type")
        if schema_type and val is not None and not _type_ok(val, schema_type):
            return {
                "error": (
                    f"Tool {fn_name} argument '{key}' should be of type "
                    f"{schema_type}, got {type(val).__name__} ({val!r})."
                )
            }
    return None