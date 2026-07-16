# OpenLCA MCP Server

Local prototype bridging Ollama (qwen3:8b) and OpenLCA via olca-ipc, exposing
ten LCA query tools through a FastMCP server. Terminal only, no cloud, no UI.

`openlca_mcp_design_v4.md` is referenced below for design rationale (§2.4,
§2.5, §6, §13, §14) but is not present in this repo -- if you have it, keep
it alongside this README; if not, this file plus the source comments are the
current source of truth.

## Prerequisites

- Python 3.11 (one venv owns both fastmcp and olca-ipc)
- OpenLCA desktop with a database loaded
- Ollama with qwen3:8b pulled

## One-time setup

```bash
python -m venv venv
source venv/bin/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
ollama pull qwen3:8b
```

## Each session

1. Open OpenLCA desktop, load database, start IPC server on port 8081
   (Tools > Developer Tools > IPC Server).
2. Make sure `ollama serve` is running. On Windows it runs as a background service.
3. Smoke test the connection:
   ```bash
   python tests/test_connection.py
   ```
   Expected: `Connected. Found N product systems.`
4. Launch the agent:
   ```bash
   python agent_loop.py
   ```

## Try it

```
> What is the climate change impact of the oil pump V1 system using TRACI 2.1?
> What processes drive that number?
```

Reference values for the oil pump V1 + TRACI 2.1 combo are in §13 of the design doc.
First call is slow (~35 s for model warmup); subsequent turns are ~4 s each.

## Project layout

```
openlca-mcp/
├── agent_loop.py        # Ollama HTTP client + MCP stdio client + REPL
├── mcp_server.py        # FastMCP wrapper, exposes tools/ via stdio
├── ipc_client.py        # Singleton olca_ipc.Client
├── config.py            # Constants (ports, model, truncation thresholds)
├── validation.py        # UUID regex + validate_args
├── logger.py            # JSONL event logger
├── tools/
│   ├── health.py        # ping_server
│   ├── systems.py       # list_product_systems, get_product_system
│   ├── lcia.py          # list_impact_methods, calculate_product_system,
│   │                    #   get_impact_contributions, get_grouped_impact_results
│   └── inventory.py     # list_processes, get_process_info, get_total_flows
├── tests/
│   ├── test_connection.py   # smoke test, runs as plain python
│   ├── test_validation.py   # pure unit tests, no IPC needed
│   ├── test_inventory.py    # pure unit tests (fuzzy matching), no IPC needed
│   └── test_tools.py        # pytest integration, needs live OpenLCA
├── requirements.txt
└── README.md
```

## Testing

```bash
# Pure unit tests, no environment needed
pytest tests/test_validation.py tests/test_inventory.py -v

# Integration tests, needs OpenLCA + IPC up
pytest tests/test_tools.py -v -s
```

`test_tools.py` skips every case if IPC is unreachable, so a clean repo can run
the full suite even with OpenLCA closed (it just won't validate much).

## Debugging

The agent writes a structured event log to `agent.log` (JSONL). Inspect live:

```bash
tail -f agent.log | jq
```

Useful event types: `ollama_request`, `ollama_response`, `tool_call`,
`tool_result`, `validation_error`, `final_answer`, `error`,
`grounding_warning` (see below).

## Accuracy hardening (new)

The local tool-calling stack this project depends on (Ollama + qwen3:8b) is
documented -- by Qwen's own function-calling guidance, and by several
Ollama/downstream-proxy issues from 2025-2026 -- to not always follow the
tool-call protocol reliably. `validation.py` and `agent_loop.py` now defend
against the specific, currently-documented failure modes rather than
assuming well-formed tool calls:

- **Stringified arguments repaired.** Several Ollama-based tool-calling
  stacks have shipped with `arguments` arriving as a JSON-encoded string
  instead of an already-parsed object. `validation.coerce_tool_args()`
  detects this and parses it; a still-malformed string gets a corrective
  error telling the model to re-issue the call with valid JSON, instead of
  either crashing or silently misbehaving downstream.
- **Unknown/hallucinated tool names rejected before dispatch**, with the
  actual list of valid tool names in the error, instead of surfacing
  whatever raw exception `mcp.call_tool()` happens to raise.
- **Schema-validated arguments before dispatch.** `validation.validate_against_schema()`
  checks the tool's own JSON `inputSchema` (already available from
  `list_tools()`, no extra round trip) for missing required fields and
  grossly wrong types, so a malformed call gets one clear, actionable error
  instead of an opaque `TypeError` from three layers down in olca-ipc. No
  new dependency (`jsonschema` is not in requirements.txt) -- this is a
  deliberately minimal structural check, not full JSON Schema semantics.
- **Non-blocking numeric-grounding diagnostic.** `agent_loop.check_numeric_grounding()`
  scans the final answer for numbers that don't appear in any tool result
  from that turn and logs a `grounding_warning` event (never edits or blocks
  the answer -- a legitimately *derived* number, like a percentage of two
  tool-returned values, won't appear verbatim and that's fine). This targets
  SYSTEM_PROMPT rule 1 ("never state a numeric value... unless it came from
  a tool result") with an actual check instead of relying on the prompt
  alone; `tail -f agent.log | jq 'select(.type=="grounding_warning")'` to spot-check.
- **Documented, not "fixed": why `call_ollama()` never passes a `think`
  key.** Explicitly combining `think` with `tools` has open Ollama bugs for
  qwen3 (empty output, or `/think`/`/no_think` tokens leaking into visible
  content). The comment in `call_ollama()` exists so a future edit doesn't
  reintroduce this by adding the parameter back "for clarity."
- **`list_processes` now falls back to fuzzy matching** (`tools/inventory.py`)
  when an exact case-insensitive substring search finds nothing. LCA
  database names are long, structured, comma-qualified strings ("aluminium
  ingot, primary, at plant") with regional-spelling and word-order variants
  a small model will often guess wrong on the first try -- returning zero
  results then costs several wasted tool-call round trips. Deliberately
  NOT plain `difflib.get_close_matches()` over whole names: tested that
  first and it scored an unrelated process above the right one, because
  whole-string edit-distance ratio is dominated by overall length on names
  this long. Uses per-token fuzzy matching instead (see
  `_token_overlap_score`'s docstring for the concrete failure case it
  fixes). The result's `fuzzy_match` field tells the caller/model whether
  matches are approximate -- present them as candidates, not a confirmed
  hit. Tests in `tests/test_inventory.py` (no IPC needed).

None of this could be verified against a live Ollama/OpenLCA connection in
the environment these changes were made in (no local model, no IPC server
available there). Verified instead by: unit tests for every new
`validation.py` function (`tests/test_validation.py`, 32 tests, runnable
with plain `python` -- no pytest needed either); and an integration-style
smoke test that stubs `fastmcp` and `requests.post` to drive `run_turn()`
through the four new failure modes end to end (not committed here since it
needs the stub scaffolding inline; recreate it if you want to re-verify
after further changes). Confirm behavior against a live model before
depending on it in production.

## Known open risks

These are flagged with `NOTE:` comments in the source where they apply.

- **Contribution entry shape** in `tools/lcia.py::get_impact_contributions`
  used `entry.tech_flow.provider.{name,id}` access. Checked against
  olca-ipc's published `ContributionItem` field list (`item: Ref, amount,
  share, rest, unit` -- no `tech_flow` field at all) without a live IPC
  connection available in this environment; **fixed** to read `.item`
  directly, with the old path kept as a defensive fallback in case an older
  olca-ipc build differs. This was a real silent-failure gap: `amount` is a
  top-level field so it always came through non-None, meaning the module's
  own `_all_amounts_none` guard never fired even though `process`/
  `process_id` were silently wrong on every row. The guard now also checks
  `process_id` (see `_all_none` in `tools/lcia.py`). Still worth confirming
  live with `test_get_impact_contributions_oil_pump` before trusting it
  fully -- this was verified against public API documentation, not a live
  probe.
- **Grouped result entry shape** in `get_grouped_impact_results` is still a
  best-guess from the method name; could not confirm the real field names
  for this one via public documentation search. Probe and adjust.
- **EnviFlowValue shape** in `get_total_flows` is still a best-guess for the
  same reason. Probe and adjust if the integration smoke test surfaces a key
  error.

## Out of scope (v0.1)

Parameter sweeps, Monte Carlo, switching background datasets, building or
modifying product systems, regionalized results, costs, normalization,
weighting, Sankey graphs.
