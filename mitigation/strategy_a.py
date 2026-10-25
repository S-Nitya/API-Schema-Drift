"""Strategy A: Schema-Diff Caching mitigation layer.

Implements lightweight, zero-LLM structural drift detection via canonical JSON hashing
and deep schema diffing.

Contract with the Agent:
    Strategy A operates purely as an advisory pre-call filter.
    - When live schema matches cached snapshot: returns action=PROCEED.
    - When live schema has drifted: returns action=RELOAD_SCHEMA, drift_detected=True,
      the live schema snapshot, a structured diff, and a human-readable reload_message.
    - On receiving RELOAD_SCHEMA, the agent is responsible for rebuilding its outbound request
      payload using the returned live schema before dispatching to the tool.
    - Strategy A NEVER mutates, drops, or dispatches the request itself.

Known Limitations:
    Strategy A compares schemas only. It CANNOT detect schema-invisible runtime drifts:
    - D2: Response format/type changes (e.g. epoch integer -> ISO-8601 string in responses).
    - D3: Value meaning/unit changes (e.g. dollars -> cents, km/h -> m/s).
    - D5: Silent null response fields (e.g. customer email silently set to None).
    These runtime/semantic drift categories are covered by Strategies B (Sanity-Check Gating)
    and C (LLM Self-Check).
"""

import copy
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from mitigation.base import Action, MitigationStrategy, PreCallResult, PostCallResult
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api

# Registry mapping canonical tool names to mock tool modules
_TOOL_MODULES: Dict[str, Any] = {
    "crm": crm_api,
    "payment": payment_api,
    "weather": weather_api,
    "search": search_api,
    "email": email_api,
}


def _resolve_tool_and_schema(tool: Union[str, Any]) -> Tuple[str, Any, Dict[str, Any]]:
    """Resolves tool identifier to (tool_name, module, live_SCHEMA).

    Enforces the 'invoke as module attribute' rule by accessing module.SCHEMA
    dynamically at call time. Never binds to static schema copies.
    """
    if isinstance(tool, str):
        key = tool.lower().replace("_api", "").strip()
        if key not in _TOOL_MODULES:
            raise ValueError(
                f"Unknown tool name '{tool}'. Known tools: {list(_TOOL_MODULES.keys())}"
            )
        module = _TOOL_MODULES[key]
        return key, module, module.SCHEMA

    if hasattr(tool, "SCHEMA"):
        module = tool
        tool_name = getattr(module, "SCHEMA", {}).get("tool")
        if not tool_name and hasattr(module, "__name__"):
            tool_name = module.__name__.split(".")[-1].replace("_api", "")
        return str(tool_name or "unknown"), module, module.SCHEMA

    raise TypeError(
        f"Tool '{tool}' must be a registered tool name (str) or a module exposing a SCHEMA attribute."
    )


def compute_schema_hash(schema: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash over a canonical JSON representation.

    Independent of dictionary key insertion order, whitespace, or execution run.
    Uses sort_keys=True, compact separators, and default=str for Python type objects.
    """
    canonical_json = json.dumps(
        schema,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _compute_diff(
    tool_name: str,
    cached_schema: Dict[str, Any],
    live_schema: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    """Computes a structured diff between cached and live schema snapshots.

    Detects:
        - Added / removed endpoints
        - Deprecated endpoints (with replacement target)
        - Added / removed request fields
        - Field rename candidates (via simple substring / token overlap heuristic)
        - Field type changes (e.g. str <-> dict)
        - Field required/optional status flips
        - Nested <-> flat structural transformations

    Rename Detection Heuristic:
        A removed field and an added field in the same endpoint are paired as candidate renames
        if either field's sanitized name is a substring of the other (e.g. 'phone' <-> 'Phone_Number').
    """
    cached_eps: Dict[str, Any] = cached_schema.get("endpoints", {})
    live_eps: Dict[str, Any] = live_schema.get("endpoints", {})

    eps_added = sorted(set(live_eps.keys()) - set(cached_eps.keys()))
    eps_removed = sorted(set(cached_eps.keys()) - set(live_eps.keys()))
    eps_deprecated: List[Dict[str, Any]] = []
    endpoint_changes: Dict[str, Any] = {}

    for ep in cached_eps:
        if ep in live_eps:
            c_ep = cached_eps[ep]
            l_ep = live_eps[ep]

            # Endpoint deprecation check (D6)
            if not c_ep.get("deprecated") and l_ep.get("deprecated"):
                eps_deprecated.append({
                    "endpoint": ep,
                    "replaced_by": l_ep.get("replaced_by"),
                    "description": l_ep.get("description", ""),
                })

            c_req: Dict[str, Any] = c_ep.get("request", {})
            l_req: Dict[str, Any] = l_ep.get("request", {})

            c_fields = set(c_req.keys())
            l_fields = set(l_req.keys())

            f_added = sorted(l_fields - c_fields)
            f_removed = sorted(c_fields - l_fields)

            # Heuristic candidate rename detection
            renamed_candidates = []
            for rf in f_removed:
                for af in f_added:
                    rf_clean = rf.lower().replace("_", "")
                    af_clean = af.lower().replace("_", "")
                    if rf_clean in af_clean or af_clean in rf_clean:
                        renamed_candidates.append({"old_field": rf, "new_field": af})

            type_changes = []
            required_changes = []
            nested_flat_changes = []

            # Compare overlapping fields
            for f in sorted(c_fields & l_fields):
                c_spec = c_req[f]
                l_spec = l_req[f]

                c_type_str = str(c_spec.get("type"))
                l_type_str = str(l_spec.get("type"))
                if c_type_str != l_type_str:
                    type_changes.append({
                        "field": f,
                        "old_type": c_type_str,
                        "new_type": l_type_str,
                    })
                    if "dict" in c_type_str or "dict" in l_type_str:
                        nested_flat_changes.append({
                            "field": f,
                            "kind": "nested_structure_shift",
                            "description": f"Field '{f}' changed between primitive and nested dict ({c_type_str} -> {l_type_str})",
                        })

                c_req_flag = c_spec.get("required")
                l_req_flag = l_spec.get("required")
                if c_req_flag != l_req_flag:
                    required_changes.append({
                        "field": f,
                        "old_required": c_req_flag,
                        "new_required": l_req_flag,
                    })

            # Check for flattening: removed dict field replaced by prefixed fields (D4)
            for rf in f_removed:
                c_spec = c_req[rf]
                if c_spec.get("type") in (dict, "dict") or "properties" in c_spec:
                    prefixed = [af for af in f_added if af.lower().startswith(rf.lower() + "_")]
                    if prefixed:
                        nested_flat_changes.append({
                            "field": rf,
                            "kind": "flattened",
                            "description": f"Nested dict '{rf}' flattened into fields: {', '.join(prefixed)}",
                        })

            # Check for nesting: removed flat fields replaced by nested dict field (D4)
            for af in f_added:
                l_spec = l_req[af]
                if l_spec.get("type") in (dict, "dict") or "properties" in l_spec:
                    prefixed = [rf for rf in f_removed if rf.lower().startswith(af.lower() + "_")]
                    if prefixed:
                        nested_flat_changes.append({
                            "field": af,
                            "kind": "nested",
                            "description": f"Flat fields ({', '.join(prefixed)}) nested into dict '{af}'",
                        })

            if f_added or f_removed or renamed_candidates or type_changes or required_changes or nested_flat_changes:
                endpoint_changes[ep] = {
                    "fields_added": f_added,
                    "fields_removed": f_removed,
                    "renamed_candidates": renamed_candidates,
                    "type_changes": type_changes,
                    "required_changes": required_changes,
                    "nested_flat_changes": nested_flat_changes,
                }

    diff: Dict[str, Any] = {
        "tool": tool_name,
        "endpoints_added": eps_added,
        "endpoints_removed": eps_removed,
        "endpoints_deprecated": eps_deprecated,
        "endpoint_changes": endpoint_changes,
    }

    # Generate human-readable reload message for agent context injection
    notes: List[str] = []
    if eps_deprecated:
        for d in eps_deprecated:
            notes.append(f"Endpoint '{d['endpoint']}' deprecated (use '{d['replaced_by']}')")
    if eps_added:
        notes.append(f"Endpoints added: {', '.join(eps_added)}")
    if eps_removed:
        notes.append(f"Endpoints removed: {', '.join(eps_removed)}")

    for ep, chg in endpoint_changes.items():
        ep_subnotes: List[str] = []
        if chg["renamed_candidates"]:
            for r in chg["renamed_candidates"]:
                ep_subnotes.append(f"field '{r['old_field']}' -> '{r['new_field']}'")

        # Added fields not part of rename
        pure_added = [
            f for f in chg["fields_added"]
            if f not in [r["new_field"] for r in chg["renamed_candidates"]]
        ]
        if pure_added:
            ep_subnotes.append(f"added {', '.join(pure_added)}")

        pure_removed = [
            f for f in chg["fields_removed"]
            if f not in [r["old_field"] for r in chg["renamed_candidates"]]
        ]
        if pure_removed:
            ep_subnotes.append(f"removed {', '.join(pure_removed)}")

        if chg["type_changes"]:
            for tc in chg["type_changes"]:
                ep_subnotes.append(f"type '{tc['field']}' ({tc['old_type']} -> {tc['new_type']})")

        if chg["required_changes"]:
            for rc in chg["required_changes"]:
                ep_subnotes.append(
                    f"required '{rc['field']}' ({rc['old_required']} -> {rc['new_required']})"
                )

        if chg["nested_flat_changes"]:
            for nfc in chg["nested_flat_changes"]:
                ep_subnotes.append(nfc["description"])

        if ep_subnotes:
            notes.append(f"{ep}: [{'; '.join(ep_subnotes)}]")

    reload_message = f"Schema drift detected for tool '{tool_name}'. " + "; ".join(notes)
    return diff, reload_message


class SchemaDiffCaching(MitigationStrategy):
    """Strategy A: Pre-call schema hash caching and structural diffing.

    Maintains per-instance cached canonical hashes of live tool schemas.
    Triggers RELOAD_SCHEMA on mismatch so the agent can rebuild requests.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._schema_fetches: int = 0
        self._hash_comparisons: int = 0
        self._drifts_detected: int = 0
        self._reloads_triggered: int = 0
        self._total_check_ns: int = 0

    def prime(self, tool: Union[str, Any]) -> str:
        """Primes the schema cache for the specified tool.

        Fetches live schema, computes canonical hash, and snapshots it in instance cache.

        Args:
            tool: Tool name string or module.

        Returns:
            The canonical SHA-256 hash string for the tool's live schema.
        """
        start_ns = time.perf_counter_ns()
        try:
            tool_name, _module, live_schema = _resolve_tool_and_schema(tool)
            self._schema_fetches += 1
            live_hash = compute_schema_hash(live_schema)
            self._cache[tool_name] = {
                "hash": live_hash,
                "schema": copy.deepcopy(live_schema),
            }
            return live_hash
        finally:
            self._total_check_ns += (time.perf_counter_ns() - start_ns)

    def pre_call(
        self,
        tool: Union[str, Any],
        endpoint: str,
        request: Dict[str, Any],
    ) -> PreCallResult:
        """Inspects live schema before request execution.

        Args:
            tool: Tool identifier (str or module).
            endpoint: Target endpoint name.
            request: Outbound request dictionary.

        Returns:
            PreCallResult with action='PROCEED' or 'RELOAD_SCHEMA'.
        """
        start_ns = time.perf_counter_ns()
        try:
            tool_name, _module, live_schema = _resolve_tool_and_schema(tool)
            self._schema_fetches += 1
            live_hash = compute_schema_hash(live_schema)

            # First encounter primes cache and proceeds
            if tool_name not in self._cache:
                self._cache[tool_name] = {
                    "hash": live_hash,
                    "schema": copy.deepcopy(live_schema),
                }
                return PreCallResult(
                    action=Action.PROCEED,
                    drift_detected=False,
                    old_hash=None,
                    new_hash=live_hash,
                    schema=copy.deepcopy(live_schema),
                    diff=None,
                    reload_message=None,
                )

            self._hash_comparisons += 1
            cached_entry = self._cache[tool_name]
            cached_hash = cached_entry["hash"]
            cached_schema = cached_entry["schema"]

            if live_hash == cached_hash:
                return PreCallResult(
                    action=Action.PROCEED,
                    drift_detected=False,
                    old_hash=cached_hash,
                    new_hash=live_hash,
                    schema=copy.deepcopy(cached_schema),
                    diff=None,
                    reload_message=None,
                )

            # Hash mismatch: structural drift detected
            self._drifts_detected += 1
            self._reloads_triggered += 1
            diff, reload_msg = _compute_diff(tool_name, cached_schema, live_schema)

            # Update cache to the newly observed schema so future calls don't re-trigger
            self._cache[tool_name] = {
                "hash": live_hash,
                "schema": copy.deepcopy(live_schema),
            }

            return PreCallResult(
                action=Action.RELOAD_SCHEMA,
                drift_detected=True,
                old_hash=cached_hash,
                new_hash=live_hash,
                schema=copy.deepcopy(live_schema),
                diff=diff,
                reload_message=reload_msg,
            )
        finally:
            self._total_check_ns += (time.perf_counter_ns() - start_ns)

    @property
    def stats(self) -> Dict[str, Any]:
        """Instrumentation metrics for cost and latency evaluation."""
        return {
            "schema_fetches": self._schema_fetches,
            "hash_comparisons": self._hash_comparisons,
            "drifts_detected": self._drifts_detected,
            "reloads_triggered": self._reloads_triggered,
            "llm_calls": 0,
            "total_check_ns": self._total_check_ns,
        }

    def reset_stats(self) -> None:
        """Resets all instrumentation counters to zero."""
        self._schema_fetches = 0
        self._hash_comparisons = 0
        self._drifts_detected = 0
        self._reloads_triggered = 0
        self._total_check_ns = 0
