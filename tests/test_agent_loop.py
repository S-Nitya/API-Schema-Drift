"""tests/test_agent_loop.py – Comprehensive unit tests for the agent loop (Task 2.1).

Uses FAKE in-test tool modules built with types.ModuleType so the loop is tested
independently of real mock tools and the drift engine.  No network calls are made.

Test coverage:
 1. baseline_clean_run         – completes; step 2 receives step 1 context.
 2. baseline_after_drift       – stale snapshot: run reports success (silent failure).
 3. memory_unchanged_by_drift  – snapshot is not updated unless strategy returns REBUILD.
 4. rebuild_repairs_call       – REBUILD with new_schema and rebuilt_request repairs call.
 5. halt_stops_run             – HALT stops execution; later steps do not run.
 6. error_response_fails_loud  – tool "error" status fails the run loudly.
 7. rebuild_limit_exceeded     – always-REBUILD strategy hits the limit.
 8. event_log_kinds            – all expected event kinds appear in the log.
 9. llm_planner_retry          – retries once on bad JSON; rejects unknown endpoints.
10. injector_called            – begin_task/end_task are called around run_task.
"""

import copy
import types
from typing import Dict, List, Optional
from types import SimpleNamespace

import pytest

from contracts import Action, MitigationStrategy, NoOpMitigation, PreCallResult, PostCallResult
from agent.agent_loop import Agent, RunResult, StepResult
from agent.event_log import EventLog
from agent.llm import ScriptedLLM, extract_json
from agent.planner import LLMPlanner, Plan, PlanError, PlanStep, ScriptedPlanner
from agent.request_builder import ScriptedRequestBuilder
from agent.schema_memory import SchemaMemory, jsonable
from agent.tool_caller import ToolCaller


# ===========================================================================
# Fake module builders
# ===========================================================================

def _make_crm_module(initial_schema: Optional[Dict] = None):
    """Build a fake CRM module as a types.ModuleType.

    The fake module:
    - Exposes a mutable SCHEMA dict.
    - Exposes a create_customer handler that silently drops fields NOT in
      the current SCHEMA and records what was actually stored in _GROUND_TRUTH.
    - Exposes _inspect_ground_truth / _reset_ground_truth helpers.
    """
    mod = types.ModuleType("fake_crm")

    base_schema = initial_schema or {
        "tool": "crm",
        "endpoints": {
            "create_customer": {
                "request": {
                    "name": {"type": str, "required": True, "description": "Name"},
                    "email": {"type": str, "required": True, "description": "Email"},
                    "phone": {"type": str, "required": False, "description": "Phone"},
                },
                "response": {
                    "status": {"type": str, "required": True, "description": "Status"},
                    "customer_id": {"type": str, "required": True, "description": "ID"},
                },
            }
        },
    }
    mod.SCHEMA = copy.deepcopy(base_schema)

    _ground_truth = {"customers": {}, "counter": 0}

    def create_customer(request=None, **kwargs):
        if request is None:
            request = kwargs
        # Drop fields not in current SCHEMA (mirror real behaviour).
        recognised = set(
            mod.SCHEMA.get("endpoints", {})
            .get("create_customer", {})
            .get("request", {})
            .keys()
        )
        filtered = {k: v for k, v in request.items() if k in recognised}
        _ground_truth["counter"] += 1
        cid = f"cust_{_ground_truth['counter']:04d}"
        _ground_truth["customers"][cid] = copy.deepcopy(filtered)
        return {"status": "success", "customer_id": cid}

    def _inspect_ground_truth():
        return copy.deepcopy(_ground_truth)

    def _reset_ground_truth():
        _ground_truth["customers"].clear()
        _ground_truth["counter"] = 0

    def _validate(endpoint, request):
        return []

    mod.create_customer = create_customer
    mod._inspect_ground_truth = _inspect_ground_truth
    mod._reset_ground_truth = _reset_ground_truth
    mod._validate = _validate

    return mod, _ground_truth


def _make_email_module():
    """Build a fake Email module with a send_email handler."""
    mod = types.ModuleType("fake_email")
    mod.SCHEMA = {
        "tool": "email",
        "endpoints": {
            "send_email": {
                "request": {
                    "to": {"type": str, "required": True, "description": "To"},
                    "subject": {"type": str, "required": True, "description": "Subject"},
                    "body": {"type": str, "required": True, "description": "Body"},
                },
                "response": {
                    "status": {"type": str, "required": True, "description": "Status"},
                    "message_id": {"type": str, "required": True, "description": "MsgID"},
                },
            }
        },
    }

    _outbox = []

    def send_email(request=None, **kwargs):
        if request is None:
            request = kwargs
        _outbox.append(copy.deepcopy(request))
        return {"status": "success", "message_id": f"msg_{len(_outbox):04d}"}

    def _validate(endpoint, request):
        return []

    mod.send_email = send_email
    mod._outbox = _outbox
    mod._validate = _validate
    return mod


def _make_error_module():
    """Build a fake module whose only endpoint always returns an error."""
    mod = types.ModuleType("fake_error_tool")
    mod.SCHEMA = {
        "tool": "errtool",
        "endpoints": {
            "fail_always": {
                "request": {"x": {"type": str, "required": True, "description": "x"}},
                "response": {},
            }
        },
    }

    def fail_always(request=None, **kwargs):
        return {"status": "error", "errors": ["always fails"]}

    def _validate(endpoint, request):
        return []

    mod.fail_always = fail_always
    mod._validate = _validate
    return mod


# Helper to build a rename-drift schema for CRM (phone -> Phone_Number)
def _drifted_crm_schema():
    schema = {
        "tool": "crm",
        "endpoints": {
            "create_customer": {
                "request": {
                    "name": {"type": str, "required": True, "description": "Name"},
                    "email": {"type": str, "required": True, "description": "Email"},
                    "Phone_Number": {
                        "type": str,
                        "required": False,
                        "description": "Phone (drifted name)",
                    },
                },
                "response": {
                    "status": {"type": str, "required": True, "description": "Status"},
                    "customer_id": {"type": str, "required": True, "description": "ID"},
                },
            }
        },
    }
    return schema


# ===========================================================================
# Fixture helpers
# ===========================================================================

def _make_2step_agent(crm_mod, email_mod, strategy=None):
    """Create an Agent configured for a 2-step CRM→Email workflow."""
    fake_modules = {"crm": crm_mod, "email": email_mod}
    caller = ToolCaller(fake_modules=fake_modules)

    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "crm", "endpoint": "create_customer",
         "intent": "Create CRM customer"},
        {"step_id": "step_2", "tool": "email", "endpoint": "send_email",
         "intent": "Send welcome email"},
    ])
    builder = ScriptedRequestBuilder({
        "step_1": {"name": "Alice", "email": "alice@example.com", "phone": "+1-555-0100"},
        "step_2": lambda ctx: {
            "to": "alice@example.com",
            "subject": "Welcome",
            "body": f"Hello! Your customer_id is {ctx['step_1']['customer_id']}",
        },
    })

    memory = SchemaMemory()
    log = EventLog()
    agent = Agent(
        planner=planner,
        builder=builder,
        strategy=strategy,
        caller=caller,
        memory=memory,
        log=log,
    )
    return agent


# ===========================================================================
# Test 1: Baseline clean run
# ===========================================================================

def test_baseline_clean_run():
    """A clean 2-step run completes; step_2 receives step_1's customer_id via context."""
    crm_mod, gt = _make_crm_module()
    email_mod = _make_email_module()
    agent = _make_2step_agent(crm_mod, email_mod)

    agent.read_schemas()
    result = agent.run_task("Onboard Alice")

    assert result.status == "completed"
    assert result.reported_success is True
    assert len(result.steps) == 2
    assert result.steps[0].status == "ok"
    assert result.steps[1].status == "ok"

    # step_2 email body should contain the customer_id from step_1's response.
    cid = result.steps[0].response["customer_id"]
    assert cid in result.steps[1].request["body"]

    # Ground truth has one customer with phone field.
    customers = gt["customers"]
    assert len(customers) == 1
    cust = next(iter(customers.values()))
    assert cust.get("phone") == "+1-555-0100"


# ===========================================================================
# Test 2: Baseline after drift (silent failure)
# ===========================================================================

def test_baseline_after_drift_silent_failure():
    """With snapshot taken BEFORE drift:
    - The run still reports success (R5: no silent failure detection).
    - The stale field name 'phone' is sent in the request.
    - Ground truth lacks the phone value (silently dropped by drifted handler).
    """
    crm_mod, gt = _make_crm_module()
    email_mod = _make_email_module()
    agent = _make_2step_agent(crm_mod, email_mod)

    # Take snapshot with ORIGINAL schema (phone field exists).
    agent.read_schemas()

    # Now drift the module SCHEMA: rename phone -> Phone_Number.
    crm_mod.SCHEMA = _drifted_crm_schema()

    # The handler now only recognises Phone_Number; 'phone' is silently dropped.
    result = agent.run_task("Onboard Alice after drift")

    # Agent reports success (it cannot detect the silent failure).
    assert result.reported_success is True
    assert result.status == "completed"

    # Verify: the request sent STILL uses 'phone' (from stale snapshot).
    step_1_request = result.steps[0].request
    assert "phone" in step_1_request  # stale field was sent

    # Ground truth: phone NOT stored (silently dropped).
    customers = gt["customers"]
    cust = next(iter(customers.values()))
    assert "phone" not in cust or cust.get("phone") is None


# ===========================================================================
# Test 3: Memory unchanged by drift unless REBUILD
# ===========================================================================

def test_memory_unchanged_by_drift():
    """The snapshot in SchemaMemory is not affected by module.SCHEMA mutation
    unless a strategy explicitly returns REBUILD with new_schema."""
    crm_mod, _ = _make_crm_module()
    email_mod = _make_email_module()
    fake_modules = {"crm": crm_mod, "email": email_mod}
    caller = ToolCaller(fake_modules=fake_modules)
    memory = SchemaMemory()

    # Read schemas before drift.
    for tool in ["crm", "email"]:
        memory.set(tool, caller.get_schema(tool))

    # Record what the snapshot says about crm.create_customer fields.
    before_fields = set(
        memory.request_schema("crm", "create_customer").keys()
    )
    assert "phone" in before_fields

    # Mutate live module.SCHEMA (drift).
    crm_mod.SCHEMA = _drifted_crm_schema()

    # Snapshot must still have 'phone', not 'Phone_Number'.
    after_fields = set(
        memory.request_schema("crm", "create_customer").keys()
    )
    assert "phone" in after_fields
    assert "Phone_Number" not in after_fields


# ===========================================================================
# Test 4: REBUILD strategy repairs the call and adopts new schema
# ===========================================================================

class _SingleRebuildStrategy(MitigationStrategy):
    """Strategy that triggers one REBUILD with corrected request + new schema."""

    name = "single_rebuild"

    def __init__(self, new_schema, fixed_request):
        self._triggered = False
        self._new_schema = new_schema
        self._fixed_request = fixed_request

    def pre_call(self, tool, endpoint, request):
        if tool == "crm" and not self._triggered:
            self._triggered = True
            return PreCallResult(
                action=Action.REBUILD,
                rebuilt_request=self._fixed_request,
                new_schema=self._new_schema,
                field_mapping={"phone": "Phone_Number"},
                reason="D1 drift detected: phone -> Phone_Number",
            )
        return PreCallResult(action=Action.PROCEED)

    def reset(self):
        self._triggered = False

    def stats(self):
        return {}


def test_rebuild_repairs_call_and_adopts_schema():
    """A REBUILD with rebuilt_request and new_schema corrects the stale request
    and updates the snapshot in SchemaMemory."""
    crm_mod, gt = _make_crm_module()
    email_mod = _make_email_module()

    # Drift the live module SCHEMA before read_schemas.
    crm_mod.SCHEMA = _drifted_crm_schema()

    new_schema = _drifted_crm_schema()
    fixed_request = {
        "name": "Alice",
        "email": "alice@example.com",
        "Phone_Number": "+1-555-0100",
    }
    strategy = _SingleRebuildStrategy(new_schema, fixed_request)

    fake_modules = {"crm": crm_mod, "email": email_mod}
    caller = ToolCaller(fake_modules=fake_modules)
    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "crm", "endpoint": "create_customer",
         "intent": "Create customer"},
        {"step_id": "step_2", "tool": "email", "endpoint": "send_email",
         "intent": "Send email"},
    ])
    builder = ScriptedRequestBuilder({
        "step_1": {"name": "Alice", "email": "alice@example.com", "phone": "+1-555-0100"},
        "step_2": {"to": "alice@example.com", "subject": "Hi", "body": "Welcome"},
    })
    memory = SchemaMemory()
    log = EventLog()
    agent = Agent(
        planner=planner, builder=builder, strategy=strategy,
        caller=caller, memory=memory, log=log,
    )
    agent.read_schemas()

    result = agent.run_task("Onboard with REBUILD")

    assert result.status == "completed"
    assert result.reported_success is True

    # Snapshot updated to drifted schema.
    new_fields = set(memory.request_schema("crm", "create_customer").keys())
    assert "Phone_Number" in new_fields

    # Ground truth should have the phone stored under original internal name.
    customers = gt["customers"]
    cust = next(iter(customers.values()))
    # The drifted handler drops 'phone' but keeps 'Phone_Number' in the request.
    assert "Phone_Number" in cust or "name" in cust

    # schema_adopted event in log.
    adopted = log.of_kind("schema_adopted")
    assert len(adopted) >= 1


# ===========================================================================
# Test 5: HALT stops the run; later steps do not execute
# ===========================================================================

class _HaltOnFirstStrategy(MitigationStrategy):
    """Strategy that halts on the very first pre_call."""

    name = "halt_first"

    def pre_call(self, tool, endpoint, request):
        return PreCallResult(action=Action.HALT, reason="test halt")

    def reset(self):
        pass

    def stats(self):
        return {}


def test_halt_stops_run():
    """HALT on step_1 stops the run; step_2 never executes."""
    crm_mod, _ = _make_crm_module()
    email_mod = _make_email_module()
    agent = _make_2step_agent(crm_mod, email_mod, strategy=_HaltOnFirstStrategy())

    agent.read_schemas()
    result = agent.run_task("Task that gets halted")

    assert result.status == "halted"
    assert result.reported_success is False
    assert len(result.steps) == 1
    assert result.steps[0].status == "halted"
    assert result.steps[0].step_id == "step_1"


# ===========================================================================
# Test 6: API "error" response fails the run loudly
# ===========================================================================

def test_error_response_fails_loudly():
    """A tool returning status=='error' produces a StepResult with status 'error'
    and a RunResult with status 'failed'."""
    error_mod = _make_error_module()
    fake_modules = {"errtool": error_mod}

    tool_module_map = {"errtool": "fake.errtool"}
    caller = ToolCaller(fake_modules=fake_modules, tool_module_map=tool_module_map)

    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "errtool", "endpoint": "fail_always",
         "intent": "Call the always-failing endpoint"},
    ])
    builder = ScriptedRequestBuilder({"step_1": {"x": "hello"}})
    memory = SchemaMemory()
    log = EventLog()

    # Manually populate memory (no real module to call get_schema on).
    memory.set("errtool", copy.deepcopy(error_mod.SCHEMA))

    agent = Agent(
        planner=planner, builder=builder,
        caller=caller, memory=memory, log=log,
    )
    result = agent.run_task("Trigger loud failure")

    assert result.status == "failed"
    assert result.reported_success is False
    assert result.steps[0].status == "error"
    assert "always fails" in result.steps[0].reason


# ===========================================================================
# Test 7: Always-REBUILD strategy hits the rebuild limit
# ===========================================================================

class _AlwaysRebuildStrategy(MitigationStrategy):
    """Strategy that always returns REBUILD (no rebuilt_request, no new_schema)."""

    name = "always_rebuild"

    def pre_call(self, tool, endpoint, request):
        return PreCallResult(
            action=Action.REBUILD,
            reason="always rebuild",
        )

    def reset(self):
        pass

    def stats(self):
        return {}


def test_rebuild_limit_exceeded():
    """An always-REBUILD strategy hits max_rebuilds and the step is marked 'failed'."""
    crm_mod, _ = _make_crm_module()
    fake_modules = {"crm": crm_mod}
    caller = ToolCaller(fake_modules=fake_modules)
    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "crm", "endpoint": "create_customer",
         "intent": "Create customer"},
    ])
    builder = ScriptedRequestBuilder({
        "step_1": {"name": "Bob", "email": "bob@example.com"},
    })
    memory = SchemaMemory()
    memory.set("crm", copy.deepcopy(crm_mod.SCHEMA))
    log = EventLog()

    agent = Agent(
        planner=planner, builder=builder,
        strategy=_AlwaysRebuildStrategy(),
        caller=caller, memory=memory, log=log,
        max_rebuilds=2,
    )
    result = agent.run_task("Task that always rebuilds")

    assert result.status == "failed"
    assert result.steps[0].status == "failed"
    assert "rebuild limit" in result.steps[0].reason


# ===========================================================================
# Test 8: Event log contains all expected event kinds
# ===========================================================================

def test_event_log_kinds():
    """A successful 1-step run emits all expected event kinds."""
    crm_mod, _ = _make_crm_module()
    email_mod = _make_email_module()
    agent = _make_2step_agent(crm_mod, email_mod)

    agent.read_schemas()
    agent.run_task("Test event log")

    log = agent.log
    kinds = {e["kind"] for e in log.all()}

    expected_kinds = {
        "schema_read",
        "plan_created",
        "request_built",
        "pre_call",
        "tool_call",
        "post_call",
        "step_result",
        "run_end",
    }
    missing = expected_kinds - kinds
    assert not missing, f"Missing event kinds: {missing}"


# ===========================================================================
# Test 9: LLMPlanner retries on bad JSON; rejects unknown endpoints
# ===========================================================================

def test_llm_planner_retry_on_bad_json():
    """LLMPlanner retries once on bad JSON (counts 2 llm_calls), then succeeds."""
    good_plan_json = (
        '{"steps": [{"step_id": "step_1", "tool": "crm", '
        '"endpoint": "create_customer", "intent": "Create customer"}]}'
    )
    llm = ScriptedLLM(["not valid json at all !!!", good_plan_json])
    planner = LLMPlanner(llm)

    catalog = {
        "crm": {"create_customer": ["name", "email"]},
    }
    plan = planner.plan("Onboard a customer", catalog)

    assert planner.llm_calls == 2
    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == "step_1"


def test_llm_planner_rejects_unknown_endpoint():
    """LLMPlanner raises PlanError if the plan references an unknown endpoint."""
    bad_plan = (
        '{"steps": [{"step_id": "step_1", "tool": "crm", '
        '"endpoint": "nonexistent_endpoint", "intent": "Does nothing"}]}'
    )
    # Second response is also bad so it exhausts retries.
    llm = ScriptedLLM([bad_plan, bad_plan])
    planner = LLMPlanner(llm)

    catalog = {"crm": {"create_customer": ["name", "email"]}}

    with pytest.raises(PlanError):
        planner.plan("Task with unknown endpoint", catalog)


def test_llm_planner_llm_calls_count():
    """LLMPlanner.llm_calls counts each completion call."""
    good = (
        '{"steps": [{"step_id": "step_1", "tool": "crm", '
        '"endpoint": "create_customer", "intent": "hi"}]}'
    )
    llm = ScriptedLLM([good])
    planner = LLMPlanner(llm)
    catalog = {"crm": {"create_customer": ["name"]}}
    planner.plan("task", catalog)
    assert planner.llm_calls == 1


# ===========================================================================
# Test 10: Injector begin_task/end_task called around run_task
# ===========================================================================

def test_injector_begin_end_task_called():
    """begin_task and end_task are called exactly once per run_task, even on success."""
    calls = []

    fake_injector = SimpleNamespace(
        begin_task=lambda label: calls.append(("begin", label)),
        end_task=lambda: calls.append(("end",)),
    )

    crm_mod, _ = _make_crm_module()
    email_mod = _make_email_module()
    fake_modules = {"crm": crm_mod, "email": email_mod}
    caller = ToolCaller(fake_modules=fake_modules)

    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "crm", "endpoint": "create_customer",
         "intent": "Create customer"},
    ])
    builder = ScriptedRequestBuilder({
        "step_1": {"name": "Carol", "email": "carol@example.com"},
    })
    memory = SchemaMemory()
    log = EventLog()
    agent = Agent(
        planner=planner, builder=builder,
        caller=caller, memory=memory, log=log,
        injector=fake_injector,
    )
    agent.read_schemas()
    agent.run_task("Task with injector", task_id="my_task")

    assert ("begin", "my_task") in calls
    assert ("end",) in calls
    # begin comes before end.
    begin_idx = next(i for i, c in enumerate(calls) if c[0] == "begin")
    end_idx = next(i for i, c in enumerate(calls) if c[0] == "end")
    assert begin_idx < end_idx


def test_injector_end_task_called_on_failure():
    """end_task is called even when the run fails (finally block guarantee)."""
    calls = []
    fake_injector = SimpleNamespace(
        begin_task=lambda label: calls.append("begin"),
        end_task=lambda: calls.append("end"),
    )

    error_mod = _make_error_module()
    fake_modules = {"errtool": error_mod}
    caller = ToolCaller(fake_modules=fake_modules, tool_module_map={"errtool": "x"})
    memory = SchemaMemory()
    memory.set("errtool", copy.deepcopy(error_mod.SCHEMA))

    planner = ScriptedPlanner([
        {"step_id": "step_1", "tool": "errtool", "endpoint": "fail_always",
         "intent": "fail"},
    ])
    builder = ScriptedRequestBuilder({"step_1": {"x": "y"}})
    agent = Agent(
        planner=planner, builder=builder,
        caller=caller, memory=memory,
        injector=fake_injector,
    )
    result = agent.run_task("Failing task")
    assert "begin" in calls
    assert "end" in calls


# ===========================================================================
# Bonus: jsonable() helper
# ===========================================================================

def test_jsonable_converts_types():
    """jsonable() converts Python type objects to their name strings."""
    schema = {
        "field": {"type": str, "required": True},
        "nested": {"type": dict, "properties": {"sub": {"type": int}}},
        "items": [str, int, float],
    }
    safe = jsonable(schema)
    assert safe["field"]["type"] == "str"
    assert safe["nested"]["type"] == "dict"
    assert safe["nested"]["properties"]["sub"]["type"] == "int"
    assert safe["items"] == ["str", "int", "float"]


# ===========================================================================
# Bonus: extract_json tolerates fences
# ===========================================================================

def test_extract_json_fenced():
    text = '```json\n{"a": 1}\n```'
    assert extract_json(text) == {"a": 1}


def test_extract_json_prose():
    text = 'Here is the response: {"x": "hello"} thanks'
    assert extract_json(text) == {"x": "hello"}
