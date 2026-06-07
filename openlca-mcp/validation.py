"""Pre-dispatch arg validation.

Two layers:

1. UUID_RE catches malformed UUIDs (wrong length, non-hex chars).
2. UuidRegistry catches invented-but-syntactically-valid UUIDs by tracking
   what the listing/calc tools have actually returned this session, with
   per-type buckets so a flow_id can't be passed as a process_id.

The model has been observed inventing UUIDs that pass the regex but don't
exist in the database. The registry is the only thing that catches those.
"""

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