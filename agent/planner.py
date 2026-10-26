"""agent/planner.py – Task decomposition into executable step plans.

Produces a ``Plan`` (list of ``PlanStep`` objects) from a natural-language task
description and the current schema catalog.  Two implementations are provided:

- ``LLMPlanner``:     real planner backed by any ``LLMClient``.
- ``ScriptedPlanner``: deterministic twin for tests and experiments.

Both expose an integer ``llm_calls`` attribute.
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from agent.llm import LLMClient, ScriptedLLM, extract_json


class PlanStep(BaseModel):
    """A single step in an execution plan.

    Attributes:
        step_id: Unique string identifier for this step (e.g. ``"step_1"``).
        tool: Tool name (must exist in the schema catalog).
        endpoint: Endpoint name within the tool.
        intent: Human-readable description of what this step does.
    """

    step_id: str
    tool: str
    endpoint: str
    intent: str


class Plan(BaseModel):
    """An ordered list of steps to execute for a task.

    Attributes:
        steps: One or more PlanSteps in execution order.
    """

    steps: List[PlanStep]

    @model_validator(mode="after")
    def _at_least_one_step(self) -> "Plan":
        if not self.steps:
            raise ValueError("Plan must contain at least one step")
        return self


class PlanError(Exception):
    """Raised when the planner cannot produce a valid plan after retries."""


# ---------------------------------------------------------------------------
# System prompt template for LLMPlanner
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are a task planner for an AI agent that controls a set of API tools.
Your job is to decompose a natural-language task into an ordered list of API calls.

Available tools and endpoints (from the schema catalog):
{catalog_str}

Respond with ONLY a JSON object in this exact format:
{{
  "steps": [
    {{"step_id": "step_1", "tool": "<tool>", "endpoint": "<endpoint>", "intent": "<what this step does>"}},
    ...
  ]
}}

Rules:
- Only use tools and endpoints that appear in the catalog above.
- step_id must be unique within the plan and follow the pattern "step_N".
- intent must be a concise human-readable description.
- Include at least one step.
- Reply with ONLY the JSON object, no prose before or after it.
"""


class LLMPlanner:
    """Task planner backed by an LLM.

    Sends the task and catalog to the LLM and parses a ``Plan``.  On malformed JSON
    or validation failure, retries once with the error message appended, then raises
    ``PlanError``.

    Args:
        llm: ``LLMClient`` instance to use for completions.

    Attributes:
        llm_calls: Total number of LLM completions made by this planner.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.llm_calls: int = 0

    def plan(
        self,
        task: str,
        catalog: Dict[str, Dict[str, List[str]]],
    ) -> Plan:
        """Decompose *task* into a ``Plan`` using the schema *catalog*.

        Args:
            task: Natural-language task description.
            catalog: Output of ``SchemaMemory.catalog()``.

        Returns:
            A validated ``Plan``.

        Raises:
            PlanError: If the LLM returns invalid JSON or an invalid plan after
                one retry.
        """
        catalog_str = _format_catalog(catalog)
        system = _SYSTEM_PROMPT.format(catalog_str=catalog_str)
        user = f"Task: {task}"

        last_error: Optional[str] = None
        for attempt in range(2):
            if attempt == 1 and last_error:
                user = (
                    f"Task: {task}\n\n"
                    f"Your previous response was invalid. Error: {last_error}\n"
                    "Please try again, replying with ONLY the JSON object."
                )
            raw = self._llm.complete(system, user)
            self.llm_calls += 1

            try:
                data = extract_json(raw)
            except ValueError as exc:
                last_error = f"Could not parse JSON: {exc}"
                continue

            try:
                plan = Plan(**data)
            except Exception as exc:
                last_error = f"Plan validation failed: {exc}"
                continue

            # Validate every step's tool/endpoint against the catalog
            try:
                _validate_plan_against_catalog(plan, catalog)
            except PlanError as exc:
                last_error = str(exc)
                continue

            return plan

        raise PlanError(
            f"LLMPlanner failed to produce a valid plan after 2 attempts. "
            f"Last error: {last_error}"
        )


class ScriptedPlanner:
    """Deterministic planner that always returns a fixed plan.

    Args:
        steps: List of dicts or ``PlanStep`` objects defining the plan.
            Each dict must have keys: step_id, tool, endpoint, intent.

    Attributes:
        llm_calls: Always 0 (no LLM involved).
    """

    def __init__(self, steps: List[Any]) -> None:
        parsed = []
        for s in steps:
            if isinstance(s, PlanStep):
                parsed.append(s)
            else:
                parsed.append(PlanStep(**s))
        self._plan = Plan(steps=parsed)
        self.llm_calls: int = 0

    def plan(
        self,
        task: str,
        catalog: Dict[str, Dict[str, List[str]]],
    ) -> Plan:
        """Return the fixed plan regardless of *task* and *catalog*.

        Args:
            task: Ignored.
            catalog: Ignored.

        Returns:
            The pre-set ``Plan``.
        """
        return self._plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_catalog(catalog: Dict[str, Dict[str, List[str]]]) -> str:
    """Format the catalog as readable text for inclusion in a prompt."""
    lines = []
    for tool, endpoints in sorted(catalog.items()):
        lines.append(f"Tool: {tool}")
        for ep, fields in sorted(endpoints.items()):
            lines.append(f"  Endpoint: {ep}  Fields: {', '.join(fields) or '(none)'}")
    return "\n".join(lines)


def _validate_plan_against_catalog(
    plan: Plan, catalog: Dict[str, Dict[str, List[str]]]
) -> None:
    """Raise ``PlanError`` if any step references a tool/endpoint not in the catalog."""
    for step in plan.steps:
        if step.tool not in catalog:
            raise PlanError(
                f"Step '{step.step_id}' references unknown tool '{step.tool}'. "
                f"Known tools: {sorted(catalog.keys())}"
            )
        if step.endpoint not in catalog[step.tool]:
            raise PlanError(
                f"Step '{step.step_id}' references unknown endpoint "
                f"'{step.endpoint}' on tool '{step.tool}'. "
                f"Known endpoints: {sorted(catalog[step.tool].keys())}"
            )
