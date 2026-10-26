"""agent/event_log.py – Structured run-event logging.

Provides ``EventLog``, a simple append-only log that records all agent-loop events
with sequence numbers and timestamps.  Supports filtering, JSONL export, and clearing.

Canonical event kinds:
    schema_read     – a tool schema was snapshotted into memory.
    plan_created    – a Plan was produced by the planner.
    request_built   – a request dict was produced by the builder.
    pre_call        – MitigationStrategy.pre_call() returned.
    tool_call       – a tool endpoint was invoked.
    post_call       – MitigationStrategy.post_call() returned.
    schema_adopted  – a new schema was adopted into memory after a REBUILD.
    request_rebuilt – the request was rebuilt after a REBUILD.
    step_result     – a step finished (ok / error / halted / failed).
    run_end         – the run finished.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.schema_memory import jsonable


class EventLog:
    """Append-only log of structured agent-loop events.

    Each event is a dict with at least ``seq``, ``kind``, and ``timestamp``
    keys, plus arbitrary keyword data.

    Usage::

        log = EventLog()
        log.log("schema_read", tool="crm", endpoints=["create_customer"])
        records = log.of_kind("schema_read")
        log.dump_jsonl(Path("run.jsonl"))
    """

    def __init__(self) -> None:
        self._events: List[Dict[str, Any]] = []
        self._seq: int = 0

    def log(self, kind: str, **data: Any) -> None:
        """Append an event with *kind* and arbitrary keyword data.

        Args:
            kind: Event kind string (see module docstring for canonical values).
            **data: Arbitrary key-value pairs merged into the event record.
        """
        self._seq += 1
        event = {
            "seq": self._seq,
            "kind": kind,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            **data,
        }
        self._events.append(event)

    def of_kind(self, kind: str) -> List[Dict[str, Any]]:
        """Return all events whose ``kind`` field matches *kind*.

        Args:
            kind: Event kind to filter on.

        Returns:
            List of matching event dicts (not copies).
        """
        return [e for e in self._events if e.get("kind") == kind]

    def all(self) -> List[Dict[str, Any]]:
        """Return all events in insertion order.

        Returns:
            List of event dicts.
        """
        return list(self._events)

    def clear(self) -> None:
        """Remove all events and reset the sequence counter."""
        self._events.clear()
        self._seq = 0

    def dump_jsonl(self, path: "Path") -> None:
        """Write all events to a JSON Lines file at *path*.

        Python type objects inside event data are converted to their name strings
        via :func:`agent.schema_memory.jsonable` before serialisation.

        Args:
            path: Destination file path (parent directories must exist).
        """
        path = Path(path)
        with open(path, "w", encoding="utf-8") as fh:
            for event in self._events:
                safe_event = jsonable(event)
                fh.write(json.dumps(safe_event, ensure_ascii=False) + "\n")
