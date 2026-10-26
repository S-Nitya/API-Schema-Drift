"""agent/schema_memory.py – In-memory schema snapshot store.

Holds deep-copied snapshots of tool schemas taken at session start (before any drift
is injected).  The agent ONLY reads from this store when building requests; it never
re-reads live module.SCHEMA.
"""

import copy
from typing import Dict, List, Optional


def jsonable(obj):
    """Recursively convert Python type objects to their string names.

    json.dumps raises TypeError when a schema contains raw Python type objects
    (e.g., ``str``, ``int``, ``dict``).  This helper walks the structure and
    replaces every ``type`` instance with ``type.__name__`` so the result can
    be safely serialised.

    Args:
        obj: Arbitrary Python object (dict, list, type, or primitive).

    Returns:
        A JSON-serialisable version of *obj*.
    """
    if isinstance(obj, type):
        return obj.__name__
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable(item) for item in obj]
    return obj


class SchemaMemory:
    """Stores deep-copied tool schema snapshots for use by the agent loop.

    The store is populated once at session start via ``set()``.  The agent loop
    reads from it throughout the run.  A mitigation strategy returning REBUILD
    may update an entry via ``set()`` at any time.
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, Dict] = {}

    def set(self, tool: str, schema: Dict) -> None:
        """Store a deep copy of *schema* for *tool*.

        Args:
            tool: Tool name (e.g. "crm").
            schema: Raw schema dict (may contain Python type objects).
        """
        self._schemas[tool] = copy.deepcopy(schema)

    def get(self, tool: str) -> Optional[Dict]:
        """Return the stored schema for *tool*, or None if not present.

        Args:
            tool: Tool name.

        Returns:
            Deep copy of the stored schema, or None.
        """
        schema = self._schemas.get(tool)
        if schema is None:
            return None
        return copy.deepcopy(schema)

    def tools(self) -> List[str]:
        """Return the list of tool names that have a stored schema.

        Returns:
            Sorted list of tool names.
        """
        return sorted(self._schemas.keys())

    def has_endpoint(self, tool: str, endpoint: str) -> bool:
        """Return True if *endpoint* exists in the stored schema for *tool*.

        Args:
            tool: Tool name.
            endpoint: Endpoint name within the tool.

        Returns:
            bool
        """
        schema = self._schemas.get(tool)
        if schema is None:
            return False
        return endpoint in schema.get("endpoints", {})

    def request_schema(self, tool: str, endpoint: str) -> Optional[Dict]:
        """Return the request field definitions for *tool*/*endpoint*.

        Args:
            tool: Tool name.
            endpoint: Endpoint name.

        Returns:
            Deep copy of the request schema dict, or None if not found.
        """
        schema = self._schemas.get(tool)
        if schema is None:
            return None
        req = schema.get("endpoints", {}).get(endpoint, {}).get("request")
        if req is None:
            return None
        return copy.deepcopy(req)

    def catalog(self) -> Dict[str, Dict[str, List[str]]]:
        """Return a summary catalog: ``{tool: {endpoint: [field_names]}}``.

        Used by the planner to validate plans against the known schema.

        Returns:
            Nested dict mapping tool -> endpoint -> list of request field names.
        """
        result: Dict[str, Dict[str, List[str]]] = {}
        for tool, schema in self._schemas.items():
            endpoints = schema.get("endpoints", {})
            result[tool] = {}
            for ep, ep_def in endpoints.items():
                request_fields = list(ep_def.get("request", {}).keys())
                result[tool][ep] = request_fields
        return result
