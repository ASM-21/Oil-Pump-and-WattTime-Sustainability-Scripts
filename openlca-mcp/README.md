# OpenLCA MCP Server

Local prototype bridging Ollama (qwen3:8b) and OpenLCA via olca-ipc, exposing
ten LCA query tools through a FastMCP server. Terminal only, no cloud, no UI.

See `openlca_mcp_design_v4.md` for the full design rationale.

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
│   └── test_tools.py        # pytest integration, needs live OpenLCA
├── requirements.txt
└── README.md
```

## Testing

```bash
# Pure unit tests, no environment needed
pytest tests/test_validation.py -v

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
`tool_result`, `validation_error`, `final_answer`, `error`.

## Known open risks

These are flagged with `NOTE:` comments in the source where they apply.

- **Contribution entry shape** in `tools/lcia.py::get_impact_contributions`
  uses `entry.tech_flow.provider.{name,id}` access. If a probe shows a
  different shape, adjust the access path. The integration test
  `test_get_impact_contributions_oil_pump` is the canary.
- **Grouped result entry shape** in `get_grouped_impact_results` is a
  best-guess from the method name. Same pattern: probe and adjust.
- **EnviFlowValue shape** in `get_total_flows` is a best-guess. Probe and
  adjust if the integration smoke test surfaces a key error.

## Out of scope (v0.1)

Parameter sweeps, Monte Carlo, switching background datasets, building or
modifying product systems, regionalized results, costs, normalization,
weighting, Sankey graphs.
