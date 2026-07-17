"""Central config. Keep all magic numbers and endpoints here."""

from pathlib import Path

OLCA_PORT = 8081
OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen3:8b"

# History truncation (see §6 of design doc)
N_RECENT_TURNS = 4          # turns kept in full
N_MAX_TURNS = 8             # hard cap; older turns dropped entirely

# Tool result limits
MAX_DESCRIPTORS = 50        # cap on list_processes output
MAX_CONTRIBUTIONS = 25      # cap on per-process contribution lists
MAX_FLOWS = 25              # cap on total flow lists
TOOL_RESULT_LOG_BYTES = 2048

# list_processes fuzzy fallback (see tools/inventory.py::_search_processes
# and _token_overlap_score for why this is per-token, not whole-string).
FUZZY_TOKEN_MATCH = 0.75   # difflib ratio for one query word to count as matching one name word
FUZZY_TOKEN_SCORE = 0.7    # fraction of query words that must match for a name to qualify

# get_descriptors() cache (see ipc_client.py::get_descriptors_cached).
# Short on purpose: trades a small staleness window for fewer large IPC
# round trips within one exchange, not a claim the database is immutable.
DESCRIPTOR_CACHE_TTL_S = 30

# Agent loop safety
MAX_TOOL_ITERATIONS = 10    # hard cap on tool calls per user turn
OLLAMA_TIMEOUT_S = 120      # request timeout for /api/chat

# Logging
# Anchored to this file's directory so the log lands next to the project,
# not in whatever CWD agent_loop was launched from.
LOG_PATH = str(Path(__file__).resolve().parent / "agent.log")
LOG_THINKING = True         # set False to omit qwen3 thinking content from log