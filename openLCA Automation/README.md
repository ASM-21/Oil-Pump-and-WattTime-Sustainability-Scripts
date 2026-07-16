# OpenLCA Automation

This folder contains scripts for updating and inspecting oil-pump energy values in OpenLCA through the OpenLCA IPC interface. It is separate from the `openlca-mcp/` prototype, which wraps OpenLCA queries as MCP tools for an agent workflow.

## Current status

**Prototype / local automation.** These scripts are useful for testing how measured or estimated manufacturing energy values can be pushed into an OpenLCA model, but they depend on local OpenLCA setup details that need to be documented before another user can reproduce them.

## Key files

| File | Role |
| --- | --- |
| `update_gui.py` | Tkinter GUI for viewing current process energy values, entering replacements, and triggering LCIA calculations. |
| `update_static.py` | Script-style update path for static/default energy values. |
| `OpenLCA_gui_tester_V8.py` | Earlier GUI/testing iteration. |
| `OpenLCA tester Updater.py` | Earlier update/testing script. |

## Expected workflow

1. Open OpenLCA desktop and load the oil-pump database.
2. Start the OpenLCA IPC server on the expected host/port.
3. Confirm process/product-system/LCIA method UUIDs.
4. Run the GUI or static updater script.
5. Record before/after energy values and LCIA totals.

## Recommended docs to add next

- OpenLCA version and database name.
- IPC server URL/port and whether it should be localhost or a lab machine.
- Product system, process, flow, and LCIA method IDs used for the oil-pump case study.
- Expected reference LCIA values for a smoke test.
- Screenshots after local IDs are removed or replaced with placeholders.

## Safety notes before sharing

- Replace private IP addresses, UUIDs, and database-specific identifiers with documented placeholders if the database cannot be shared. **Checked:** none of the four scripts have hardcoded IPs, filesystem paths, or UUIDs as of this pass -- all connection/ID config already goes through `os.getenv(..., "PLACEHOLDER")`.
- Explain which values come from measured machine data, CAD estimates, or assumptions.
- Keep the `openlca-mcp/README.md` as the starting point for agent-based OpenLCA querying.

## Correctness findings (new)

See [`FINDINGS.md`](FINDINGS.md) for a static-verification pass (no OpenLCA
desktop available to run these live): a real crash in `update_static.py`
(missing `import os`, now fixed) and a ~100x data-entry error in the legacy
`OpenLCA tester Updater.py` (now fixed), plus two flagged-but-unverified
risks -- an internal MJ/kWh unit contradiction in that same legacy script,
and `update_gui.py` updating Tkinter widgets from background threads.

