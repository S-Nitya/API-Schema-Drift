"""tests/test_agent_real_tools.py – Real-tool smoke tests (Step 3).

Uses the REAL mock tools and DriftInjector with ScriptedPlanner and
ScriptedRequestBuilder (no LLM) for the 3-step enterprise onboarding flow:
    CRM create_customer -> Payment charge_customer -> Email send_email

Tests:
 1. clean_baseline_run       – completes; ground truth matches expectations.
 2. baseline_after_d1_drift  – run reports success but CRM ground truth
                               lacks the phone value (silent failure).

Fixture teardown always resets the injector with ground_truth=True so state
never leaks between tests.
"""

import copy
import pytest

from drift_engine import DriftInjector
from mock_tools import (
    inspect_crm_ground_truth,
    inspect_email_ground_truth,
    inspect_payment_ground_truth,
    reset_crm_ground_truth,
    reset_email_ground_truth,
    reset_payment_ground_truth,
)

from agent.agent_loop import Agent
from agent.event_log import EventLog
from agent.planner import ScriptedPlanner
from agent.request_builder import ScriptedRequestBuilder
from agent.schema_memory import SchemaMemory
from agent.tool_caller import ToolCaller

# ---------------------------------------------------------------------------
# Shared workflow plan (valid for the real tools)
# ---------------------------------------------------------------------------
_ONBOARDING_STEPS = [
    {
        "step_id": "step_crm",
        "tool": "crm",
        "endpoint": "create_customer",
        "intent": "Create a new enterprise customer in CRM",
    },
    {
        "step_id": "step_pay",
        "tool": "payment",
        "endpoint": "charge_customer",
        "intent": "Charge the setup fee to the new customer",
    },
    {
        "step_id": "step_email",
        "tool": "email",
        "endpoint": "send_email",
        "intent": "Send an invoice receipt email",
    },
]

_ONBOARDING_REQUESTS = {
    "step_crm": {
        "name": "Acme Corp",
        "email": "billing@acme.com",
        "phone": "+1-555-0199",
        "company": "Acme Corporation",
        "status": "active",
        "address": {
            "street": "100 Innovation Way",
            "city": "Bengaluru",
            "country": "IN",
            "postal_code": "560001",
        },
    },
    "step_pay": lambda ctx: {
        "customer_id": ctx["step_crm"]["customer_id"],
        "amount": 500.0,
        "currency": "USD",
        "description": "Enterprise Onboarding Setup Fee",
        "payment_method": "card",
    },
    "step_email": lambda ctx: {
        "to": "billing@acme.com",
        "subject": "Welcome to Enterprise Sponsorship - Invoice Receipt",
        "body": (
            f"Hello Acme Corp, your account "
            f"({ctx['step_crm']['customer_id']}) is active. "
            f"We charged USD 500.00 (Tx: {ctx['step_pay']['transaction_id']})."
        ),
        "cc": ["finance@acme.com"],
        "sender": {
            "email": "accounts@events.org",
            "name": "Event Accounts Desk",
        },
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def injector():
    """Fresh DriftInjector; always resets (including ground truth) on teardown."""
    inj = DriftInjector()
    inj.reset(ground_truth=True)
    yield inj
    inj.reset(ground_truth=True)


def _reset_all():
    reset_crm_ground_truth()
    reset_payment_ground_truth()
    reset_email_ground_truth()


def _make_agent(injector_instance=None):
    """Build an Agent over the real mock tools."""
    caller = ToolCaller()
    planner = ScriptedPlanner(_ONBOARDING_STEPS)
    builder = ScriptedRequestBuilder(_ONBOARDING_REQUESTS)
    memory = SchemaMemory()
    log = EventLog()
    return Agent(
        planner=planner,
        builder=builder,
        caller=caller,
        memory=memory,
        log=log,
        injector=injector_instance,
    )


# ---------------------------------------------------------------------------
# Test 1: Clean baseline run
# ---------------------------------------------------------------------------

def test_clean_baseline_run(injector):
    """No drift: 3-step onboarding completes and ground truth is correct."""
    _reset_all()

    agent = _make_agent()
    # R1: read schemas BEFORE any drift.
    agent.read_schemas()

    result = agent.run_task(
        "Onboard Acme Corp as an enterprise client, charge $500 setup fee, "
        "and send an invoice receipt.",
        task_id="clean_run",
    )

    assert result.status == "completed", f"Run failed: {result.reason}"
    assert result.reported_success is True
    assert len(result.steps) == 3
    assert all(s.status == "ok" for s in result.steps)

    # Verify CRM ground truth.
    cid = result.context["step_crm"]["customer_id"]
    crm_gt = inspect_crm_ground_truth()
    assert cid in crm_gt["customers"], "Customer not found in CRM ground truth"
    cust = crm_gt["customers"][cid]
    assert cust["email"] == "billing@acme.com"
    assert cust.get("phone") == "+1-555-0199", (
        f"Expected phone '+1-555-0199', got {cust.get('phone')!r}"
    )
    assert cust["address"]["city"] == "Bengaluru"

    # Verify Payment ground truth.
    tx_id = result.context["step_pay"]["transaction_id"]
    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["amount"] == 500.0
    assert pay_gt["transactions"][tx_id]["customer_id"] == cid

    # Verify Email ground truth.
    msg_id = result.context["step_email"]["message_id"]
    email_gt = inspect_email_ground_truth()
    outbox = email_gt["outbox"]
    assert any(e.get("message_id") == msg_id for e in outbox), (
        "Message not found in email outbox"
    )


# ---------------------------------------------------------------------------
# Test 2: Baseline after D1 (phone -> Phone_Number drift on CRM)
# ---------------------------------------------------------------------------

def test_baseline_after_d1_drift_silent_failure(injector):
    """D1 drift injected AFTER agent.read_schemas():
    - Run still reports success (agent cannot detect silent failure).
    - CRM ground truth does NOT contain the phone value.
    """
    _reset_all()

    agent = _make_agent()

    # R1: take snapshot with original schema (phone field present).
    agent.read_schemas()

    # Inject D1 drift AFTER snapshot (simulating between-task drift).
    injector.inject("D1", "crm")

    result = agent.run_task(
        "Onboard Acme Corp (baseline after D1 drift)",
        task_id="d1_drift_run",
    )

    # Agent reports success – it has no way to detect the silent failure.
    assert result.reported_success is True, (
        "Baseline should report success even under drift"
    )
    assert result.status == "completed"

    # Verify the snapshot still has the stale field name 'phone'.
    snapshot_fields = set(
        agent.memory.request_schema("crm", "create_customer").keys()
    )
    assert "phone" in snapshot_fields
    assert "Phone_Number" not in snapshot_fields

    # Verify the request sent used 'phone' (stale field from snapshot).
    crm_step = result.steps[0]
    assert "phone" in crm_step.request

    # Verify the SILENT FAILURE: phone is NOT stored in ground truth.
    cid = result.context["step_crm"]["customer_id"]
    crm_gt = inspect_crm_ground_truth()
    cust = crm_gt["customers"][cid]
    phone_in_gt = cust.get("phone") or cust.get("Phone_Number")
    assert phone_in_gt is None, (
        f"Expected phone to be absent from ground truth (silent failure), "
        f"but got: phone={cust.get('phone')!r}, Phone_Number={cust.get('Phone_Number')!r}"
    )
