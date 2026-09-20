"""Comprehensive Test Suite for Task 1.4 Multi-Step Workflows.

Tests all 12 multi-step workflows across the 5 mock tools with:
1. Clean baseline ground-truth resets before each workflow.
2. Step-by-step response status and output structural validation.
3. Rigorous ground-truth state inspection across CRM, Payment, Email, Weather, and Search.
"""

import sys
from typing import Dict, Any

from mock_tools import (
    inspect_crm_ground_truth,
    inspect_email_ground_truth,
    inspect_payment_ground_truth,
    inspect_search_ground_truth,
    inspect_weather_ground_truth,
    reset_crm_ground_truth,
    reset_email_ground_truth,
    reset_payment_ground_truth,
    reset_search_ground_truth,
    reset_weather_ground_truth,
)
from workflows import (
    WORKFLOW_REGISTRY,
    run_workflow_01,
    run_workflow_02,
    run_workflow_03,
    run_workflow_04,
    run_workflow_05,
    run_workflow_06,
    run_workflow_07,
    run_workflow_08,
    run_workflow_09,
    run_workflow_10,
    run_workflow_11,
    run_workflow_12,
)


def reset_all_tools() -> None:
    """Resets all 5 mock tools to clean ground-truth state."""
    reset_crm_ground_truth()
    reset_payment_ground_truth()
    reset_email_ground_truth()
    reset_weather_ground_truth()
    reset_search_ground_truth()


def print_banner(title: str) -> None:
    print("\n" + "=" * 75)
    print(f" {title}")
    print("=" * 75)


def test_workflow_01() -> None:
    print("\n---> Running Workflow 01: Enterprise Client Onboarding...")
    reset_all_tools()
    res = run_workflow_01()

    assert res["status"] == "success", f"W01 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3, f"Expected 3 steps, got {len(res['steps'])}"
    for step in res["steps"]:
        assert step["response"].get("status") == "success", f"Step failed: {step}"

    # Ground truth verification
    cust_id = res["outputs"]["customer_id"]
    tx_id = res["outputs"]["transaction_id"]
    msg_id = res["outputs"]["message_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"], "Customer not found in CRM ground truth"
    cust_record = crm_gt["customers"][cust_id]
    assert cust_record["email"] == "billing@acme.com"
    assert cust_record["address"]["city"] == "Bengaluru"

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"], "Transaction not found in Payment ground truth"
    assert pay_gt["transactions"][tx_id]["amount"] == 500.0
    assert pay_gt["transactions"][tx_id]["customer_id"] == cust_id

    email_gt = inspect_email_ground_truth()
    assert any(e["message_id"] == msg_id for e in email_gt["outbox"]), "Email not found in ground truth outbox"
    print("[PASS] Workflow 01 PASSED with ground-truth verification")


def test_workflow_02() -> None:
    print("\n---> Running Workflow 02: Event Refund Notification...")
    reset_all_tools()
    res = run_workflow_02()

    assert res["status"] == "success", f"W02 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    # Ground truth verification
    tx_id = res["outputs"]["transaction_id"]
    ref_id = res["outputs"]["refund_id"]

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["refunded_amount"] == 75.0
    assert pay_gt["transactions"][tx_id]["transaction_status"] == "refunded"
    assert ref_id in pay_gt["refunds"]
    assert pay_gt["refunds"][ref_id]["amount_refunded"] == 75.0

    email_gt = inspect_email_ground_truth()
    assert any("Refund Confirmation" in e["subject"] for e in email_gt["outbox"])
    print("[PASS] Workflow 02 PASSED with ground-truth verification")


def test_workflow_03() -> None:
    print("\n---> Running Workflow 03: Coastal Weather Safety Advisory...")
    reset_all_tools()
    res = run_workflow_03()

    assert res["status"] == "success", f"W03 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    assert res["outputs"]["city"] == "Mumbai"
    assert res["outputs"]["temperature"] == 28.5

    email_gt = inspect_email_ground_truth()
    assert any("Mumbai Coastal Venue Status" in e["subject"] for e in email_gt["outbox"])
    print("[PASS] Workflow 03 PASSED with ground-truth verification")


def test_workflow_04() -> None:
    print("\n---> Running Workflow 04: Venue Forecast Reminder...")
    reset_all_tools()
    res = run_workflow_04()

    assert res["status"] == "success", f"W04 failed: {res.get('errors')}"
    assert len(res["steps"]) == 2
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    assert res["outputs"]["city"] == "Delhi"
    assert res["outputs"]["forecast_days"] == 3

    email_gt = inspect_email_ground_truth()
    assert any(e["send_at"] == 1700014400 for e in email_gt["outbox"])
    print("[PASS] Workflow 04 PASSED with ground-truth verification")


def test_workflow_05() -> None:
    print("\n---> Running Workflow 05: Cancellation Email Audit and Ticket Refund...")
    reset_all_tools()
    res = run_workflow_05()

    assert res["status"] == "success", f"W05 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    cust_id = res["outputs"]["customer_id"]
    tx_id = res["outputs"]["transaction_id"]
    ref_id = res["outputs"]["refund_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"]

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["refunded_amount"] == 75.0
    assert ref_id in pay_gt["refunds"]
    print("[PASS] Workflow 05 PASSED with ground-truth verification")


def test_workflow_06() -> None:
    print("\n---> Running Workflow 06: VIP Sponsorship Registration and Billing...")
    reset_all_tools()
    res = run_workflow_06()

    assert res["status"] == "success", f"W06 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    cust_id = res["outputs"]["customer_id"]
    tx_id = res["outputs"]["transaction_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"]
    assert crm_gt["customers"][cust_id]["metadata"]["annual_revenue"] == 500000.0

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["amount"] == 1200.0
    print("[PASS] Workflow 06 PASSED with ground-truth verification")


def test_workflow_07() -> None:
    print("\n---> Running Workflow 07: Emergency Weather Bulletin Distribution...")
    reset_all_tools()
    res = run_workflow_07()

    assert res["status"] == "success", f"W07 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    assert res["outputs"]["city"] == "Bengaluru"

    email_gt = inspect_email_ground_truth()
    assert any("URGENT: Weather Action Bulletin" in e["subject"] for e in email_gt["outbox"])
    print("[PASS] Workflow 07 PASSED with ground-truth verification")


def test_workflow_08() -> None:
    print("\n---> Running Workflow 08: Customer Profile Address Update and Email Verification...")
    reset_all_tools()
    res = run_workflow_08()

    assert res["status"] == "success", f"W08 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    cust_id = res["outputs"]["customer_id"]
    msg_id = res["outputs"]["message_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"]
    assert crm_gt["customers"][cust_id]["phone"] == "+91-9123456789"
    assert crm_gt["customers"][cust_id]["address"]["street"] == "77 Brigade Road"

    email_gt = inspect_email_ground_truth()
    assert any(e["message_id"] == msg_id for e in email_gt["outbox"])
    print("[PASS] Workflow 08 PASSED with ground-truth verification")


def test_workflow_09() -> None:
    print("\n---> Running Workflow 09: Equipment Weather Guidelines Check...")
    reset_all_tools()
    res = run_workflow_09()

    assert res["status"] == "success", f"W09 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    assert res["outputs"]["city"] == "Chennai"
    assert res["outputs"]["primary_document"]["id"] == "doc_003"
    print("[PASS] Workflow 09 PASSED with ground-truth verification")


def test_workflow_10() -> None:
    print("\n---> Running Workflow 10: Customer Billing Audit and Transaction Verification...")
    reset_all_tools()
    res = run_workflow_10()

    assert res["status"] == "success", f"W10 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    cust_id = res["outputs"]["customer_id"]
    tx_id = res["outputs"]["transaction_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"]

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["amount"] == 150.0
    print("[PASS] Workflow 10 PASSED with ground-truth verification")


def test_workflow_11() -> None:
    print("\n---> Running Workflow 11: Venue Weather Assessment and Contingency Planning...")
    reset_all_tools()
    res = run_workflow_11()

    assert res["status"] == "success", f"W11 failed: {res.get('errors')}"
    assert len(res["steps"]) == 3
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    assert res["outputs"]["city"] == "Pune"
    assert res["outputs"]["forecast_count"] == 2
    assert res["outputs"]["search_matches"] > 0
    print("[PASS] Workflow 11 PASSED with ground-truth verification")


def test_workflow_12() -> None:
    print("\n---> Running Workflow 12: Sponsor Booth Booking and Delivery Verification...")
    reset_all_tools()
    res = run_workflow_12()

    assert res["status"] == "success", f"W12 failed: {res.get('errors')}"
    assert len(res["steps"]) == 4
    for step in res["steps"]:
        assert step["response"].get("status") == "success"

    cust_id = res["outputs"]["customer_id"]
    tx_id = res["outputs"]["transaction_id"]
    msg_id = res["outputs"]["message_id"]

    crm_gt = inspect_crm_ground_truth()
    assert cust_id in crm_gt["customers"]

    pay_gt = inspect_payment_ground_truth()
    assert tx_id in pay_gt["transactions"]
    assert pay_gt["transactions"][tx_id]["amount"] == 350.0

    email_gt = inspect_email_ground_truth()
    assert any(e["message_id"] == msg_id for e in email_gt["outbox"])
    print("[PASS] Workflow 12 PASSED with ground-truth verification")


def test_all_workflows_via_registry() -> None:
    print_banner("Testing All 12 Workflows via Master Registry")
    assert len(WORKFLOW_REGISTRY) == 12, f"Expected 12 workflows, found {len(WORKFLOW_REGISTRY)}"

    for wid, item in WORKFLOW_REGISTRY.items():
        reset_all_tools()
        runner = item["runner"]
        res = runner()
        assert res["status"] == "success", f"Workflow {wid} ({item['name']}) returned error: {res.get('errors')}"
        assert res["workflow_id"] == wid
        assert len(res["steps"]) >= 2
        print(f"[PASS] Registry execution verified: {wid} - {item['name']} ({len(res['steps'])} steps)")


if __name__ == "__main__":
    print_banner("Running Task 1.4 Full Workflow Suite Test Suite")
    test_workflow_01()
    test_workflow_02()
    test_workflow_03()
    test_workflow_04()
    test_workflow_05()
    test_workflow_06()
    test_workflow_07()
    test_workflow_08()
    test_workflow_09()
    test_workflow_10()
    test_workflow_11()
    test_workflow_12()
    test_all_workflows_via_registry()
    print_banner("ALL 12 WORKFLOWS PASSED GROUND-TRUTH VALIDATION")
