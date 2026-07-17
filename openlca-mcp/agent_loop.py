"""Terminal agent loop.

Spawns mcp_server.py over stdio, pulls tool schemas, REPLs against Ollama,
dispatches tool calls back through MCP. See §2.4 of the design doc.

Run with OpenLCA + IPC up, ollama serve up:
    python agent_loop.py

Slash commands:
    /reset    Wipe history (keeps the MCP connection open).
    /refresh  Force-refresh the cached process/product-system/method lists.
    /help     Show available slash commands.
    /tools    List available tools.
"""

import asyncio
import copy
import json
import re
import sys
import time
from pathlib import Path

import requests
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from config import (
    LOG_THINKING,
    MAX_TOOL_ITERATIONS,
    MODEL_NAME,
    N_MAX_TURNS,
    N_RECENT_TURNS,
    OLLAMA_TIMEOUT_S,
    OLLAMA_URL,
    TOOL_RESULT_LOG_BYTES,
)
from ipc_client import clear_descriptor_cache
from logger import log_event
from validation import (
    UuidRegistry,
    coerce_tool_args,
    validate_against_schema,
    validate_args,
)


SYSTEM_PROMPT = """You answer questions about life cycle assessment data in an OpenLCA database. You have tools that query the database directly.

ABSOLUTE RULES:
1. Never state a numeric impact value, percentage, kg CO2-Eq amount, or process name unless it came from a tool result in this conversation. Inventing values is the worst thing you can do.
2. Never invent UUIDs. UUIDs are 36-character strings that come ONLY from tool results. The system rejects unknown UUIDs.
3. Do not write tutorials, hypothetical examples, or "here is how you would..." explanations. Call the tools and report what they return.

WORKFLOW for impact questions:
- If you do not have the product_system_id, call list_product_systems first.
- If you do not have the method_id, call list_impact_methods first.
- To get any impact value, call calculate_product_system. It returns ALL impact categories at once. Do not call it twice for the same system+method.
- For "what is driving this number" questions, call get_impact_contributions with the impact_category_id from a prior calculate_product_system result. The category_id is on each impact entry returned.
- For inventory flow questions, call get_total_flows.
- For process detail questions, call list_processes to find the id, then get_process_info.

If a tool returns an error, report it plainly to the user and stop. Do not retry with guessed parameters.

Always include units. Units come from the tool result, not your memory. Examples: kg CO2-Eq, kg SO2-Eq, CTUe, CTUh.
"""


# Few-shot example of a correct tool-calling trajectory, injected into
# history as real turn-formatted messages (not prose inside SYSTEM_PROMPT).
# Per current tool-calling literature (e.g. the LangChain few-shot-for-
# tool-calling writeup), models handle genuine role-tagged example messages
# better than the same content flattened into one system-prompt string, and
# few-shot examples measurably improve tool-calling precision for smaller
# models -- exactly this project's situation (qwen3:8b). Uses obviously
# placeholder UUIDs (sequential, all-zero prefix) so the model can't mistake
# them for real, reusable IDs; the point is demonstrating the CALL SHAPE and
# ordering (discover before use, ground the final number, include units),
# not IDs to remember. One example only, covering the workflow SYSTEM_PROMPT
# spends the most words on (impact calculation) -- kept to one to bound
# token overhead on an 8B model's context; add a second (e.g. the
# tool-error-then-stop rule) only after checking token budget on the actual
# deployment, since this could not be tuned against a live model here.
#
# IMPORTANT: truncate_history() is written to always preserve this preamble
# verbatim (see preserve_prefix_len) so it survives no matter how long the
# real conversation grows -- do not reorder this above SYSTEM_PROMPT or
# change its length without also checking every call site below that passes
# len(FEWSHOT_MESSAGES).
FEWSHOT_MESSAGES: list = [
    {"role": "user", "content": "What is the climate change impact of the oil pump V1 system using TRACI 2.1?"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "ex_1", "function": {"name": "list_product_systems", "arguments": {}}},
    ]},
    {"role": "tool", "tool_call_id": "ex_1", "content": json.dumps(
        {"systems": [{"id": "00000000-0000-4000-8000-000000000001", "name": "Oil Pump V1"}], "count": 1}
    )},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "ex_2", "function": {"name": "list_impact_methods", "arguments": {}}},
    ]},
    {"role": "tool", "tool_call_id": "ex_2", "content": json.dumps(
        {"methods": [{"id": "00000000-0000-4000-8000-000000000002",
                      "name": "TRACI 2.1", "description": "US EPA TRACI 2.1"}], "count": 1}
    )},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "ex_3", "function": {"name": "calculate_product_system", "arguments": {
            "product_system_id": "00000000-0000-4000-8000-000000000001",
            "method_id": "00000000-0000-4000-8000-000000000002",
        }}},
    ]},
    {"role": "tool", "tool_call_id": "ex_3", "content": json.dumps({
        "impacts": [
            {"category": "Climate change", "category_id": "00000000-0000-4000-8000-000000000003",
             "amount": 32.32, "unit": "kg CO2-Eq"},
            {"category": "Acidification", "category_id": "00000000-0000-4000-8000-000000000004",
             "amount": 0.18, "unit": "kg SO2-Eq"},
        ],
        "count": 2,
    })},
    {"role": "assistant",
     "content": "The climate change impact of Oil Pump V1 under TRACI 2.1 is 32.32 kg CO2-Eq.",
     "tool_calls": []},
]


SLASH_HELP = """Slash commands:
  /reset    Wipe history (MCP connection stays open, no model warmup penalty).
  /refresh  Force-refresh the process/product-system/method list cache
            (use if you changed the OpenLCA database mid-session).
  /tools    List available tools.
  /help     Show this message.
  (empty)   Exit."""


# ---------- Schema conversion ----------

def convert_to_ollama(tool) -> dict:
    """Convert a FastMCP tool descriptor to OpenAI-style function schema."""
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


# ---------- Ollama HTTP ----------

def call_ollama(history: list, tools: list) -> dict:
    """POST to Ollama /api/chat. Returns the full response dict.

    Deliberately does NOT pass a "think" key. Ollama's qwen3 handling has
    open bugs where explicitly combining think=true (or false) with the
    tools parameter produces empty output or leaks /think and /no_think
    tokens into visible content (ollama/ollama issues #10976, #14601, as of
    2025-2026). Omitting the key and taking Ollama's default for this model
    is the path that is actually known to return usable `message.thinking`
    content (see the LOG_THINKING handling below) -- don't "fix" this by
    adding an explicit think parameter without re-checking those issues.
    """
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL_NAME,
            "messages": history,
            "tools": tools,
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


# ---------- History truncation (§6) ----------

def _turn_starts(history: list, start_at: int = 0) -> list:
    """Indices (>= start_at) of user-role messages, plus an end sentinel."""
    starts = [i for i, m in enumerate(history) if i >= start_at and m.get("role") == "user"]
    starts.append(len(history))
    return starts


def truncate_history(history: list, preserve_prefix_len: int = 0) -> list:
    """Apply §6 truncation rules in place. Returns the same list for chaining.

    1. Keep system prompt always.
    2. Keep the next `preserve_prefix_len` messages always, verbatim, and
       excluded from turn-counting -- for FEWSHOT_MESSAGES, a fixed example
       transcript that should never be dropped or stubbed no matter how long
       the real conversation grows (defaults to 0, reproducing the exact
       original behavior for any caller that doesn't pass it).
    3. Keep current turn intact.
    4. Keep last N_RECENT_TURNS in full.
    5. Older turns: stub tool messages to a small preview.
    6. Drop everything older than N_MAX_TURNS turns.

    Important: turns are dropped or kept whole, never split. This preserves
    the assistant-with-tool_calls -> tool-result pairing that Ollama requires.
    """
    has_system = bool(history) and history[0].get("role") == "system"
    base = (1 if has_system else 0) + preserve_prefix_len

    starts = _turn_starts(history, start_at=base)
    user_starts = starts[:-1]
    n_turns = len(user_starts)

    if n_turns <= N_RECENT_TURNS:
        return history

    # Drop turns older than N_MAX_TURNS (whole turns, never partial)
    if n_turns > N_MAX_TURNS:
        cutoff = user_starts[-N_MAX_TURNS]
        kept = list(history[:base])
        kept.extend(history[cutoff:])
        history.clear()
        history.extend(kept)
        starts = _turn_starts(history, start_at=base)
        user_starts = starts[:-1]
        n_turns = len(user_starts)

    # Stub tool messages in turns older than N_RECENT_TURNS
    if n_turns > N_RECENT_TURNS:
        recent_cutoff = user_starts[-N_RECENT_TURNS]
        for i in range(base, recent_cutoff):
            msg = history[i]
            if msg.get("role") == "tool" and not msg.get("_summarized"):
                original = msg.get("content", "")
                msg["content"] = json.dumps(
                    {"_summarized": True, "preview": original[:150]}
                )
                msg["_summarized"] = True

    return history


# ---------- Tool result extraction ----------

def extract_payload(call_result) -> dict:
    """Pull a JSON-serializable dict out of a FastMCP CallToolResult."""
    data = getattr(call_result, "data", None)
    if data is not None:
        return data if isinstance(data, dict) else {"value": data}

    content = getattr(call_result, "content", None) or []
    if content:
        first = content[0]
        text = getattr(first, "text", None)
        if text:
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                return {"value": text}

    return {"value": str(call_result)}


# ---------- Grounding diagnostic (non-blocking) ----------

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _numbers_in(text: str) -> set:
    return {m.replace(",", "") for m in _NUMBER_RE.findall(text)}


def check_numeric_grounding(final_answer: str, turn_tool_contents: list) -> list:
    """Non-blocking diagnostic: numbers stated in the final answer that don't
    appear in any tool result returned during this turn are suspicious --
    possibly fabricated rather than read off a real result, the specific
    failure mode SYSTEM_PROMPT rule 1 forbids. This never edits or blocks
    the answer (the model may legitimately compute a derived number, e.g. a
    percentage of two tool-returned values, that won't appear verbatim); it
    only logs a warning so the transcript can be spot-checked. Skips
    magnitude-under-10 numbers since those are usually counts/indices
    restated in prose (e.g. "3 categories"), not values worth fact-checking.
    """
    grounded = set()
    for content in turn_tool_contents:
        grounded |= _numbers_in(content)
    suspicious = []
    for n in _numbers_in(final_answer):
        try:
            if abs(float(n)) < 10:
                continue
        except ValueError:
            continue
        if n not in grounded:
            suspicious.append(n)
    return suspicious


# ---------- Display helpers ----------

def _short_args(args: dict) -> str:
    """One-line preview of args for the tool-call announcement."""
    if not args:
        return ""
    pairs = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 12:
            s = s[:8] + ".."
        pairs.append(f"{k}={s}")
    return ", ".join(pairs)


# ---------- Turn loop ----------

async def run_turn(
    history: list,
    ollama_tools: list,
    mcp: Client,
    registry: UuidRegistry,
    tool_schemas: dict | None = None,
) -> None:
    """Loop until the model produces a no-tool-call response.

    tool_schemas maps tool name -> its JSON inputSchema (from
    convert_to_ollama), used for pre-dispatch structural validation. Optional
    and defaults to no schema checking so this function still works if a
    caller doesn't have schemas handy.
    """
    tool_schemas = tool_schemas or {}
    known_tool_names = set(tool_schemas.keys())
    turn_tool_contents: list = []
    iterations = 0
    while True:
        if iterations >= MAX_TOOL_ITERATIONS:
            msg = f"[Reached MAX_TOOL_ITERATIONS ({MAX_TOOL_ITERATIONS}). Stopping turn.]"
            print(f"\n{msg}")
            log_event("error", phase="run_turn", reason="max_iterations")
            return
        iterations += 1

        truncate_history(history, preserve_prefix_len=len(FEWSHOT_MESSAGES))
        log_event(
            "ollama_request",
            model=MODEL_NAME,
            tool_count=len(ollama_tools),
            history_length=len(history),
            iteration=iterations,
        )

        t0 = time.time()
        try:
            response = await asyncio.to_thread(call_ollama, history, ollama_tools)
        except Exception as e:
            log_event("error", phase="ollama", type=type(e).__name__, message=str(e))
            print(f"\n[ollama error] {e}")
            return
        latency = time.time() - t0

        msg = response.get("message", {})
        tool_calls = msg.get("tool_calls", []) or []
        thinking = msg.get("thinking") or ""

        log_payload = {
            "content": (msg.get("content") or "")[:500],
            "tool_calls": [tc.get("function", {}).get("name") for tc in tool_calls],
            "thinking_len": len(thinking),
            "latency": round(latency, 2),
        }
        if LOG_THINKING:
            log_payload["thinking"] = thinking
        log_event("ollama_response", **log_payload)

        # Append cleaned assistant message (drop `thinking` per §2.5)
        history.append(
            {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", ""),
                "tool_calls": tool_calls,
            }
        )

        if not tool_calls:
            final = msg.get("content", "")
            print(f"\n{final}")
            suspicious = check_numeric_grounding(final, turn_tool_contents)
            if suspicious:
                log_event("grounding_warning", numbers=suspicious, content=final[:500])
            log_event("final_answer", content=final)
            return

        # Dispatch each tool call
        for tc in tool_calls:
            tc_id = tc.get("id", "")
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            log_event("tool_call", id=tc_id, name=name, args=raw_args)

            # Repair the documented Ollama failure mode where `arguments`
            # arrives as a JSON-encoded string instead of an object, before
            # any further validation (including the live preview below)
            # assumes it's already a dict.
            args, coerce_err = coerce_tool_args(raw_args, name)

            # Live announce so the user can see what's happening
            args_preview = _short_args(args or {})
            preview_str = f"({args_preview})" if args_preview else "()"
            print(f"  -> {name}{preview_str}", flush=True)

            if coerce_err is not None:
                log_event(
                    "validation_error", id=tc_id, name=name, args=raw_args,
                    reason=coerce_err["error"],
                )
                history.append({
                    "role": "tool", "tool_call_id": tc_id,
                    "content": json.dumps(coerce_err),
                })
                continue

            if known_tool_names and name not in known_tool_names:
                err = {
                    "error": (
                        f"Unknown tool '{name}'. Available tools: "
                        f"{', '.join(sorted(known_tool_names))}. "
                        "Call one of these exact names."
                    )
                }
                log_event(
                    "validation_error", id=tc_id, name=name, args=args,
                    reason=err["error"],
                )
                history.append({
                    "role": "tool", "tool_call_id": tc_id,
                    "content": json.dumps(err),
                })
                continue

            err = validate_against_schema(name, args, tool_schemas.get(name))
            if err is None:
                err = validate_args(name, args, registry)
            if err is not None:
                log_event(
                    "validation_error",
                    id=tc_id,
                    name=name,
                    args=args,
                    reason=err["error"],
                )
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(err),
                    }
                )
                continue

            try:
                call_result = await mcp.call_tool(name, args)
                payload = extract_payload(call_result)
            except Exception as e:
                payload = {"error": f"{type(e).__name__}: {e}"}
                log_event(
                    "error",
                    phase="tool_dispatch",
                    name=name,
                    type=type(e).__name__,
                    message=str(e),
                )

            # Track UUIDs from the result so future calls can be validated
            if isinstance(payload, dict) and "error" not in payload:
                registry.track_result(name, payload)

            content_str = json.dumps(payload, default=str)
            turn_tool_contents.append(content_str)
            log_event(
                "tool_result",
                id=tc_id,
                name=name,
                preview=content_str[:TOOL_RESULT_LOG_BYTES],
                size_bytes=len(content_str),
            )
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content_str,
                }
            )


# ---------- Slash commands ----------

def handle_slash(
    cmd: str,
    history: list,
    registry: UuidRegistry,
    tools: list,
) -> bool:
    """Handle a slash command. Returns True if handled, False otherwise."""
    cmd = cmd.lower().strip()

    if cmd in ("/reset", "/clear"):
        # Keep the system message and the few-shot preamble, drop everything else
        sys_msg = history[0] if history and history[0].get("role") == "system" else None
        history.clear()
        if sys_msg is not None:
            history.append(sys_msg)
        history.extend(copy.deepcopy(FEWSHOT_MESSAGES))
        registry.clear()
        log_event("reset")
        print("[history cleared]")
        return True

    if cmd == "/refresh":
        clear_descriptor_cache()
        log_event("refresh")
        print("[descriptor cache cleared -- next list_processes/list_product_systems/"
              "list_impact_methods call will re-fetch from OpenLCA]")
        return True

    if cmd in ("/help", "/?"):
        print(SLASH_HELP)
        return True

    if cmd == "/tools":
        for t in tools:
            desc = (t.description or "").strip().split("\n")[0]
            print(f"  {t.name}: {desc}")
        return True

    return False


# ---------- Entry point ----------

async def amain() -> None:
    server_script = Path(__file__).resolve().parent / "mcp_server.py"
    transport = PythonStdioTransport(
        script_path=str(server_script),
        python_cmd=sys.executable,
    )
    client = Client(transport)

    async with client as mcp:
        tools = await mcp.list_tools()
        ollama_tools = [convert_to_ollama(t) for t in tools]
        tool_schemas = {
            ot["function"]["name"]: ot["function"]["parameters"]
            for ot in ollama_tools
        }
        log_event("startup", tools=[t.name for t in tools], model=MODEL_NAME)

        history: list = [{"role": "system", "content": SYSTEM_PROMPT}]
        history.extend(copy.deepcopy(FEWSHOT_MESSAGES))
        registry = UuidRegistry()

        print(f"OpenLCA agent ready. {len(tools)} tools, model {MODEL_NAME}.")
        print("Type /help for commands, empty line to exit.\n")

        while True:
            try:
                user_input = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            user_input = user_input.strip()
            if not user_input:
                break

            if user_input.startswith("/"):
                if handle_slash(user_input, history, registry, tools):
                    continue
                # fall through if unrecognized; treat as user input

            log_event("user_input", text=user_input)
            history.append({"role": "user", "content": user_input})

            try:
                await run_turn(history, ollama_tools, mcp, registry, tool_schemas)
            except Exception as e:
                log_event("error", phase="run_turn", type=type(e).__name__, message=str(e))
                print(f"\n[turn error] {e}")


if __name__ == "__main__":
    asyncio.run(amain())