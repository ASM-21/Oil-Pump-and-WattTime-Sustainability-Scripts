"""Append-only JSONL logger. Inspect with `tail -f agent.log | jq`."""

import json
import time
from pathlib import Path

from config import LOG_PATH

_PATH = Path(LOG_PATH)


def log_event(event_type: str, **payload) -> None:
    record = {"ts": time.time(), "type": event_type, **payload}
    with _PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
