"""agent/agent_loop.py – The core agent execution loop.

Hosts the full pipeline:
    User task -> Planner -> [for each step] -> RequestBuilder
    -> MitigationStrategy.pre_call -> ToolCaller.call
    -> MitigationStrategy.post_call -> context accumulation

Design rules enforced here:
    R1. Requests are built from SNAPSHOT schema; live module.SCHEMA is never read.
    R3. The agent is strategy-agnostic; it only talks to MitigationStrategy.
    R4. Event data is run through jsonable() before logging.
    R5. status=="error" is a loud failure; the agent never detects silent failures.
    R6. All timing via time.perf_counter.
"""

import copy
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from contracts import Action, MitigationStrategy, NoOpMitigation, PreCallResult
from agent.event_log import EventLog
from agent.planner import Plan, PlanError
from agent.request_builder import ScriptedRequestBuilder
from agent.schema_memory import SchemaMemory, jsonable
from agent.tool_caller import ToolCaller


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    """Outcome of a single plan step execution.

    Attributes:
        step_id: Matches ``PlanStep.step_id``.
        tool: Tool name used.
        endpoint: Endpoint name called.
        status: One of ``"ok"``, ``"error"``, ``"halted"``, ``"failed"``.
            - ``"ok"``     – tool returned status=="success".
            - ``"error"``  – tool returned status=="error" (loud failure).
            - ``"halted"`` – a strategy returned HALT.
            - ``"failed"`` – exception thrown by the tool or rebuild limit exceeded.
        request: Request dict that was ultimately sent.
        response: Response dict returned (or {} if halted/failed before a call).
        attempts: Number of tool invocations made for this step.
        reason: Human-readable explanation (for non-ok statuses).
    """

    step_id: str
    tool: str
    endpoint: str
    status: str  # "ok" | "error" | "halted" | "failed"
    request: Dict
    response: Dict
    attempts: int
    reason: str = ""


@dataclass
class RunResult:
    """Outcome of a complete run_task execution.

    Attributes:
        run_id: Unique run identifier (UUID4).
        status: One of ``"completed"``, ``"halted"``, ``"failed"``.
        reported_success: True iff every step returned status=="success".
            The agent cannot detect silent failures; a run reporting success
            may still have corrupted ground truth due to schema drift.
        steps: List of StepResult objects.
        context: Final accumulated context dict (step_id -> response).
        reason: Human-readable explanation (for non-completed statuses).
        llm_calls: LLM completions made during this run (planner + builder).
        tool_calls: Actual tool invocations made.
        elapsed_s: Wall-clock seconds for the run.
    """

    run_id: str
    status: str  # "completed" | "halted" | "failed"
    reported_success: bool
    steps: List[StepResult]
    context: Dict[str, Dict]
    reason: str = ""
    llm_calls: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class Agent:
    """Orchestrates planning, request building, and tool calling for a task.

    Args:
        planner: Planner instance (LLMPlanner or ScriptedPlanner).
        builder: RequestBuilder instance (LLMRequestBuilder or ScriptedRequestBuilder).
        strategy: MitigationStrategy to use.  ``None`` defaults to ``NoOpMitigation``
            (baseline – no corrections applied).
        caller: ToolCaller instance.  A default instance with the real tool map is
            created if not provided.
        memory: SchemaMemory instance.  A fresh instance is created if not provided.
        log: EventLog instance.  A fresh instance is created if not provided.
        injector: Optional DriftInjector.  If supplied, ``begin_task``/``end_task``
            are called around each ``run_task`` invocation.
        max_rebuilds: Maximum number of REBUILD loops per step before the step
            is marked as ``"failed"`` with reason ``"rebuild limit exceeded"``.
    """

    def __init__(
        self,
        planner: Any,
        builder: Any,
        strategy: Optional[MitigationStrategy] = None,
        caller: Optional[ToolCaller] = None,
        memory: Optional[SchemaMemory] = None,
        log: Optional[EventLog] = None,
        injector: Optional[Any] = None,
        max_rebuilds: int = 2,
    ) -> None:
        self._planner = planner
        self._builder = builder
        self._strategy: MitigationStrategy = strategy or NoOpMitigation()
        self._caller: ToolCaller = caller or ToolCaller()
        self._memory: SchemaMemory = memory or SchemaMemory()
        self._log: EventLog = log or EventLog()
        self._injector = injector
        self._max_rebuilds = max_rebuilds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def memory(self) -> SchemaMemory:
        """The schema memory store used by this agent."""
        return self._memory

    @property
    def log(self) -> EventLog:
        """The event log used by this agent."""
        return self._log

    def read_schemas(self, tools: Optional[List[str]] = None) -> None:
        """Snapshot tool schemas into memory BEFORE any drift is injected.

        This method reads ``module.SCHEMA`` once via ``ToolCaller.get_schema``,
        stores a deep copy in ``SchemaMemory``, and calls
        ``strategy.on_schema_read`` (Strategy A uses this to prime its cache).

        Rule R1: After this call the agent loop NEVER re-reads live module.SCHEMA.

        Args:
            tools: List of tool names to snapshot.  Defaults to all known tools.
        """
        tool_list = tools or self._caller.tool_names()
        for tool in tool_list:
            schema = self._caller.get_schema(tool)
            self._memory.set(tool, schema)
            self._strategy.on_schema_read(tool, copy.deepcopy(schema))
            endpoints = list(schema.get("endpoints", {}).keys())
            self._log.log(
                "schema_read",
                tool=tool,
                endpoints=endpoints,
            )

    def run_task(
        self,
        task: str,
        task_id: Optional[str] = None,
    ) -> RunResult:
        """Execute *task* end-to-end and return a ``RunResult``.

        If the memory snapshot is empty, ``read_schemas()`` is called once first
        (Rule R1 fallback).

        Args:
            task: Natural-language task description.
            task_id: Optional label passed to ``injector.begin_task``.  Defaults to
                a short UUID-based label.

        Returns:
            A ``RunResult`` summarising the run.
        """
        # Ensure schema snapshot exists.
        if not self._memory.tools():
            self.read_schemas()

        run_id = str(uuid.uuid4())
        label = task_id or f"run_{run_id[:8]}"
        t_start = time.perf_counter()

        # Bookkeeping for delta llm_calls / tool_calls
        llm_calls_before = (
            getattr(self._planner, "llm_calls", 0)
            + getattr(self._builder, "llm_calls", 0)
        )
        tool_calls: int = 0

        # Wrap with injector if provided.
        if self._injector is not None:
            self._injector.begin_task(label)

        step_results: List[StepResult] = []
        context: Dict[str, Dict] = {}

        try:
            # ----------------------------------------------------------------
            # Planning phase (uses SNAPSHOT catalog)
            # ----------------------------------------------------------------
            catalog = self._memory.catalog()
            try:
                plan: Plan = self._planner.plan(task, catalog)
            except PlanError as exc:
                elapsed = time.perf_counter() - t_start
                llm_delta = (
                    getattr(self._planner, "llm_calls", 0)
                    + getattr(self._builder, "llm_calls", 0)
                    - llm_calls_before
                )
                result = RunResult(
                    run_id=run_id,
                    status="failed",
                    reported_success=False,
                    steps=[],
                    context={},
                    reason=f"Planning failed: {exc}",
                    llm_calls=llm_delta,
                    tool_calls=0,
                    elapsed_s=elapsed,
                )
                self._log.log(
                    "run_end",
                    run_id=run_id,
                    status="failed",
                    reason=result.reason,
                    strategy=self._strategy.name,
                )
                return result

            self._log.log(
                "plan_created",
                run_id=run_id,
                steps=[
                    {"step_id": s.step_id, "tool": s.tool, "endpoint": s.endpoint}
                    for s in plan.steps
                ],
            )

            # ----------------------------------------------------------------
            # Execution phase
            # ----------------------------------------------------------------
            run_status = "completed"
            run_reason = ""

            for step in plan.steps:
                # Verify endpoint exists in SNAPSHOT.
                if not self._memory.has_endpoint(step.tool, step.endpoint):
                    sr = StepResult(
                        step_id=step.step_id,
                        tool=step.tool,
                        endpoint=step.endpoint,
                        status="failed",
                        request={},
                        response={},
                        attempts=0,
                        reason=(
                            f"Endpoint '{step.endpoint}' not found in snapshot "
                            f"for tool '{step.tool}'"
                        ),
                    )
                    step_results.append(sr)
                    self._log.log("step_result", **_step_result_dict(sr))
                    run_status = "failed"
                    run_reason = sr.reason
                    break

                # Build the initial request from the SNAPSHOT request schema.
                req_schema = self._memory.request_schema(step.tool, step.endpoint)
                request = self._builder.build(task, step, req_schema, context)
                self._log.log(
                    "request_built",
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    request=jsonable(request),
                )

                sr = self._execute_step(
                    task=task,
                    step=step,
                    request=request,
                    context=context,
                    step_results=step_results,
                )
                tool_calls += sr.attempts
                step_results.append(sr)
                self._log.log("step_result", **_step_result_dict(sr))

                if sr.status == "ok":
                    context[step.step_id] = sr.response
                elif sr.status == "halted":
                    run_status = "halted"
                    run_reason = sr.reason
                    break
                else:
                    # "error" or "failed"
                    run_status = "failed"
                    run_reason = sr.reason
                    break

        finally:
            if self._injector is not None:
                self._injector.end_task()

        # Determine reported_success: True iff every step returned ok.
        reported_success = (
            run_status == "completed"
            and all(sr.status == "ok" for sr in step_results)
        )

        elapsed = time.perf_counter() - t_start
        llm_delta = (
            getattr(self._planner, "llm_calls", 0)
            + getattr(self._builder, "llm_calls", 0)
            - llm_calls_before
        )

        result = RunResult(
            run_id=run_id,
            status=run_status,
            reported_success=reported_success,
            steps=step_results,
            context=context,
            reason=run_reason,
            llm_calls=llm_delta,
            tool_calls=tool_calls,
            elapsed_s=elapsed,
        )

        self._log.log(
            "run_end",
            run_id=run_id,
            status=run_status,
            reported_success=reported_success,
            llm_calls=llm_delta,
            tool_calls=tool_calls,
            elapsed_s=round(elapsed, 4),
            strategy=self._strategy.name,
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        task: str,
        step: Any,
        request: Dict,
        context: Dict[str, Dict],
        step_results: List[StepResult],
    ) -> StepResult:
        """Run one plan step through the pre_call -> call -> post_call loop.

        Handles HALT, REBUILD (with bounded retries), and PROCEED actions from
        the mitigation strategy.

        Returns:
            A ``StepResult`` describing the outcome.
        """
        rebuild_count = 0
        attempts = 0

        while True:
            # --- Pre-call hook ---
            self._log.log(
                "pre_call",
                step_id=step.step_id,
                tool=step.tool,
                endpoint=step.endpoint,
                request=jsonable(request),
            )
            pre = self._strategy.pre_call(step.tool, step.endpoint, request)

            if pre.action == Action.HALT:
                return StepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    status="halted",
                    request=request,
                    response={},
                    attempts=attempts,
                    reason=pre.reason or "Strategy halted the step",
                )

            if pre.action == Action.REBUILD:
                rebuild_count += 1
                if rebuild_count > self._max_rebuilds:
                    return StepResult(
                        step_id=step.step_id,
                        tool=step.tool,
                        endpoint=step.endpoint,
                        status="failed",
                        request=request,
                        response={},
                        attempts=attempts,
                        reason="rebuild limit exceeded",
                    )
                # Adopt new schema if strategy supplies one.
                if pre.new_schema is not None:
                    self._memory.set(step.tool, pre.new_schema)
                    self._log.log(
                        "schema_adopted",
                        step_id=step.step_id,
                        tool=step.tool,
                        reason=pre.reason,
                    )

                if pre.rebuilt_request is not None:
                    request = pre.rebuilt_request
                else:
                    # Rebuild from updated snapshot with hints.
                    req_schema = self._memory.request_schema(step.tool, step.endpoint)
                    hints = {
                        "field_mapping": pre.field_mapping,
                        "reason": pre.reason,
                    }
                    request = self._builder.build(task, step, req_schema, context, hints=hints)
                self._log.log(
                    "request_rebuilt",
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    rebuild_count=rebuild_count,
                    request=jsonable(request),
                )
                # Re-run pre_call on the new request (loop continues).
                continue

            # pre.action == Action.PROCEED → call the tool.
            self._log.log(
                "tool_call",
                step_id=step.step_id,
                tool=step.tool,
                endpoint=step.endpoint,
                request=jsonable(request),
            )
            try:
                response = self._caller.call(step.tool, step.endpoint, request)
                attempts += 1
            except Exception as exc:
                return StepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    status="failed",
                    request=request,
                    response={},
                    attempts=attempts + 1,
                    reason=f"Tool call raised exception: {exc}",
                )

            # --- Post-call hook ---
            post = self._strategy.post_call(
                step.tool, step.endpoint, request, response
            )
            self._log.log(
                "post_call",
                step_id=step.step_id,
                tool=step.tool,
                endpoint=step.endpoint,
                action=post.action.value,
                reason=post.reason,
            )

            if post.action == Action.HALT:
                return StepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    status="halted",
                    request=request,
                    response=response,
                    attempts=attempts,
                    reason=post.reason or "Strategy halted after call",
                )

            if post.action == Action.REBUILD:
                rebuild_count += 1
                if rebuild_count > self._max_rebuilds:
                    return StepResult(
                        step_id=step.step_id,
                        tool=step.tool,
                        endpoint=step.endpoint,
                        status="failed",
                        request=request,
                        response=response,
                        attempts=attempts,
                        reason="rebuild limit exceeded",
                    )
                if post.new_schema is not None:
                    self._memory.set(step.tool, post.new_schema)
                    self._log.log(
                        "schema_adopted",
                        step_id=step.step_id,
                        tool=step.tool,
                        reason=post.reason,
                    )
                # Rebuild request and retry from top of loop.
                req_schema = self._memory.request_schema(step.tool, step.endpoint)
                request = self._builder.build(task, step, req_schema, context)
                self._log.log(
                    "request_rebuilt",
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    rebuild_count=rebuild_count,
                    request=jsonable(request),
                )
                continue

            # post.action == Action.PROCEED
            final_response = post.response if post.response is not None else response

            # R5: loud failure on status=="error"
            if final_response.get("status") == "error":
                return StepResult(
                    step_id=step.step_id,
                    tool=step.tool,
                    endpoint=step.endpoint,
                    status="error",
                    request=request,
                    response=final_response,
                    attempts=attempts,
                    reason=str(final_response.get("errors", "tool error")),
                )

            return StepResult(
                step_id=step.step_id,
                tool=step.tool,
                endpoint=step.endpoint,
                status="ok",
                request=request,
                response=final_response,
                attempts=attempts,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step_result_dict(sr: StepResult) -> Dict:
    """Convert a StepResult to a loggable dict."""
    return {
        "step_id": sr.step_id,
        "tool": sr.tool,
        "endpoint": sr.endpoint,
        "status": sr.status,
        "attempts": sr.attempts,
        "reason": sr.reason,
        "response_status": sr.response.get("status") if sr.response else None,
    }
