"""agent/request_builder.py – Builds API request dicts from task context.

Provides:
- ``LLMRequestBuilder``: uses an LLM to construct a valid request dict from the
  task description, step intent, schema, and prior-step context.
- ``ScriptedRequestBuilder``: deterministic twin returning pre-set dicts or callables.

Both expose an integer ``llm_calls`` attribute.
"""

from typing import Any, Callable, Dict, List, Optional, Union

from agent.llm import LLMClient, extract_json
from agent.schema_memory import jsonable


# ---------------------------------------------------------------------------
# System prompt template for LLMRequestBuilder
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are an API request builder for an AI agent.
Your job is to construct a valid JSON request object for a specific API endpoint.

Rules:
- Use ONLY field names that appear in the request schema below.
- Include ALL required fields.
- Omit optional fields that have no value available from the task or context.
- Take field values from the task description and the outputs of earlier steps.
- Reply with ONLY a JSON object, no prose, no markdown fences.

Request schema for {tool}.{endpoint}:
{schema_str}

Outputs from earlier steps (context):
{context_str}
"""


class LLMRequestBuilder:
    """Builds API request dicts using an LLM.

    Args:
        llm: ``LLMClient`` instance.

    Attributes:
        llm_calls: Total LLM completions made by this builder.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.llm_calls: int = 0

    def build(
        self,
        task: str,
        step: Any,  # PlanStep
        request_schema: Dict,
        context: Dict[str, Dict],
        hints: Optional[Dict] = None,
    ) -> Dict:
        """Build a request dict for *step* using the LLM.

        Args:
            task: Natural-language task description.
            step: ``PlanStep`` being executed.
            request_schema: Deep copy of the request field definitions.
            context: Outputs from prior steps keyed by step_id.
            hints: Optional dict with ``field_mapping`` and ``reason`` from a
                strategy REBUILD result; appended to the user prompt.

        Returns:
            Dict that can be passed to the tool endpoint.
        """
        schema_str = _format_schema(request_schema)
        context_str = _format_context(context)

        system = _SYSTEM_PROMPT.format(
            tool=step.tool,
            endpoint=step.endpoint,
            schema_str=schema_str,
            context_str=context_str,
        )
        user = (
            f"Task: {task}\n"
            f"Current step intent: {step.intent}"
        )
        if hints:
            mapping = hints.get("field_mapping", {})
            reason = hints.get("reason", "")
            if mapping:
                user += f"\n\nField mapping hint (old -> new names): {mapping}"
            if reason:
                user += f"\nReason: {reason}"

        raw = self._llm.complete(system, user)
        self.llm_calls += 1
        return extract_json(raw)


class ScriptedRequestBuilder:
    """Deterministic request builder that returns pre-set dicts or callables.

    Args:
        step_responses: Dict mapping step_id -> dict or callable(context) -> dict.
            If a callable is provided it receives the current context dict and should
            return the request dict.

    Attributes:
        llm_calls: Always 0 (no LLM involved).
    """

    def __init__(
        self,
        step_responses: Dict[str, Union[Dict, Callable[[Dict], Dict]]],
    ) -> None:
        self._step_responses = step_responses
        self.llm_calls: int = 0

    def build(
        self,
        task: str,
        step: Any,  # PlanStep
        request_schema: Dict,
        context: Dict[str, Dict],
        hints: Optional[Dict] = None,
    ) -> Dict:
        """Return the pre-set request for *step*.

        Args:
            task: Ignored.
            step: ``PlanStep`` whose ``step_id`` is used to look up the response.
            request_schema: Ignored.
            context: Passed to callable responses.
            hints: Ignored.

        Returns:
            Pre-set request dict.

        Raises:
            KeyError: If *step.step_id* is not in the step_responses map.
        """
        value = self._step_responses[step.step_id]
        if callable(value):
            return value(context)
        return dict(value)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_schema(request_schema: Dict) -> str:
    """Format the request schema as human-readable text for the prompt."""
    lines = []
    for field_name, field_def in request_schema.items():
        required = field_def.get("required", False)
        type_name = field_def.get("type")
        if isinstance(type_name, type):
            type_name = type_name.__name__
        desc = field_def.get("description", "")
        req_marker = "(required)" if required else "(optional)"
        lines.append(f"  {field_name} [{type_name}] {req_marker}: {desc}")
        props = field_def.get("properties", {})
        for p_name, p_def in props.items():
            p_type = p_def.get("type")
            if isinstance(p_type, type):
                p_type = p_type.__name__
            p_req = p_def.get("required", False)
            p_desc = p_def.get("description", "")
            p_req_marker = "(required)" if p_req else "(optional)"
            lines.append(f"    .{p_name} [{p_type}] {p_req_marker}: {p_desc}")
    return "\n".join(lines) if lines else "(no fields)"


def _format_context(context: Dict[str, Dict]) -> str:
    """Format prior-step outputs as human-readable text for the prompt."""
    if not context:
        return "(none)"
    lines = []
    for step_id, response in context.items():
        lines.append(f"  {step_id}: {response}")
    return "\n".join(lines)
