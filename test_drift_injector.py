"""Comprehensive test suite for the Drift Injection Engine (Task 1.3).

Tests:
1. All 30 target cells (6 drift types x 5 tools) with schema diff assertions, call assertions, and reset verification.
2. Silent failure demonstration (D1 on CRM).
3. Simultaneous drift stacking across multiple tools.
4. Mid-task injection guard enforcement.
5. Deterministic log generation.
6. Post-reset regression check ensuring original tool integration test passes.
"""

import copy
import sys
from drift_engine import (
    ConflictingDriftError,
    DriftInjector,
    InvalidDriftError,
    MidTaskInjectionError,
    UnknownToolError,
)
from drift_engine.drift_injector import DRIFT_CATALOG, _TOOL_MODULES
import test_all_tools_integration


def print_banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def test_30_cells() -> None:
    print_banner("Test 1: Testing All 30 Catalog Drift Cells (6 Drifts x 5 Tools)")
    injector = DriftInjector()

    for (drift_id, tool_name), spec in DRIFT_CATALOG.items():
        module = _TOOL_MODULES[tool_name]
        orig_schema = copy.deepcopy(module.SCHEMA)

        print(f"\n---> Testing Cell ({drift_id}, {tool_name}): {spec['drift_name']}")

        # 1. Inject drift
        record = injector.inject(drift_id, tool_name)
        assert record["drift_id"] == drift_id
        assert record["tool"] == tool_name

        # 2. Schema visibility check
        if spec["schema_visible"]:
            assert module.SCHEMA != orig_schema, f"SCHEMA expected to differ for ({drift_id}, {tool_name})"
        else:
            assert module.SCHEMA == orig_schema, f"SCHEMA expected to be identical for ({drift_id}, {tool_name})"

        # 3. Behavioral check based on drift type
        module._reset_ground_truth()

        if drift_id == "D1":
            if tool_name == "crm":
                res1 = module.create_customer({"name": "Test User", "email": "test@ex.com", "Phone_Number": "+12345"})
                assert res1["status"] == "success"
                gt = module._inspect_ground_truth()["customers"][res1["customer_id"]]
                assert gt.get("phone") == "+12345"
            elif tool_name == "payment":
                res = module.charge_customer({"customer_id": "c1", "amount": 10.0, "statement_descriptor": "Test Memo"})
                assert res["status"] == "success"
                gt = module._inspect_ground_truth()["transactions"][res["transaction_id"]]
                assert gt.get("description") == "Test Memo"
            elif tool_name == "weather":
                res = module.get_current_weather({"city": "Mumbai", "country": "IN"})
                assert res["status"] == "success"
            elif tool_name == "search":
                res = module.search({"query": "event", "limit": 2})
                assert res["status"] == "success"
                assert len(res["results"]) <= 2
            elif tool_name == "email":
                res = module.send_email({"to": "a@b.com", "subject": "Hi", "body": "Body", "carbon_copy": ["c@b.com"]})
                assert res["status"] == "success"

        elif drift_id == "D2":
            if tool_name == "crm":
                res = module.create_customer({"name": "Test User", "email": "test@ex.com"})
                assert isinstance(res["created_at"], str) and "T" in res["created_at"]
            elif tool_name == "payment":
                res = module.charge_customer({"customer_id": "c1", "amount": 50.0})
                assert res["amount"] == "50.00"
            elif tool_name == "weather":
                res = module.get_current_weather({"city": "Mumbai"})
                assert res["humidity"].endswith("%")
            elif tool_name == "search":
                res = module.search({"query": "event"})
                assert isinstance(res["results"][0]["score"], str)
            elif tool_name == "email":
                res = module.send_email({"to": "a@b.com", "subject": "Hi", "body": "Body"})
                assert isinstance(res["queued_at"], str) and "T" in res["queued_at"]

        elif drift_id == "D3":
            if tool_name == "crm":
                res = module.create_customer({"name": "Test User", "email": "t@e.com", "metadata": {"annual_revenue": 50000}})
                get_res = module.get_customer({"customer_id": res["customer_id"]})
                assert get_res["customer"]["metadata"]["annual_revenue"] == 50.0
            elif tool_name == "payment":
                res = module.charge_customer({"customer_id": "c1", "amount": 50.0})
                assert res["amount"] == 5000.0
            elif tool_name == "weather":
                res = module.get_current_weather({"city": "Mumbai"})
                # Mumbai orig wind_speed is 4.5 m/s -> 16.2 km/h
                assert res["wind_speed"] == 16.2
            elif tool_name == "search":
                res = module.search({"query": "Outdoor Event Safety Guidelines"})
                # Score transformed to distance 1 - score
                assert res["results"][0]["score"] < 0.5
            elif tool_name == "email":
                # Request send_at in ms 1700000000000 -> handler receives seconds 1700000000
                res = module.send_email({"to": "a@b.com", "subject": "Hi", "body": "Body", "send_at": 1700000000000})
                assert res["status"] == "success"
                gt = module._inspect_ground_truth()["outbox"][0]
                assert gt["send_at"] == 1700000000

        elif drift_id == "D4":
            if tool_name == "crm":
                res = module.create_customer({
                    "name": "Test", "email": "t@e.com",
                    "address_street": "123 Street", "address_city": "Mumbai"
                })
                assert res["status"] == "success"
                get_res = module.get_customer({"customer_id": res["customer_id"]})
                assert get_res["customer"].get("address_street") == "123 Street"
            elif tool_name == "payment":
                res = module.charge_customer({"customer_id": "c1", "amount": 10.0, "payment_method": {"type": "wallet"}})
                assert res["status"] == "success"
            elif tool_name == "weather":
                res = module.get_current_weather({"location": {"city": "Mumbai", "country_code": "IN"}})
                assert res["status"] == "success"
            elif tool_name == "search":
                res = module.search({"query": "event", "filter_category": "guidelines"})
                assert res["status"] == "success"
            elif tool_name == "email":
                res = module.send_email({
                    "to": "a@b.com", "subject": "Hi", "body": "Body",
                    "sender_email": "boss@co.com", "sender_name": "Boss"
                })
                assert res["status"] == "success"

        elif drift_id == "D5":
            if tool_name == "crm":
                c = module.create_customer({"name": "Test", "email": "t@e.com"})
                get_res = module.get_customer({"customer_id": c["customer_id"]})
                assert get_res["customer"]["email"] is None
            elif tool_name == "payment":
                res = module.charge_customer({"customer_id": "c1", "amount": 10.0})
                assert res["transaction_id"] is None
            elif tool_name == "weather":
                res = module.get_current_weather({"city": "Mumbai"})
                assert res["temperature"] is None
            elif tool_name == "search":
                res = module.search({"query": "event"})
                assert res["results"][0]["id"] is None
            elif tool_name == "email":
                res = module.send_email({"to": "a@b.com", "subject": "Hi", "body": "Body"})
                assert res["message_id"] is None

        elif drift_id == "D6":
            if tool_name == "crm":
                assert hasattr(module, "get_customer_v2")
                res = module.get_customer({"customer_id": "cust_9999"})
                assert res["status"] == "success"
                assert res["customer"]["name"] == "Placeholder Customer"
            elif tool_name == "payment":
                assert hasattr(module, "refund_customer_v2")
                res = module.refund_customer({"transaction_id": "tx_0001"})
                assert res["status"] == "success"
                assert res["amount_refunded"] == 0.0
            elif tool_name == "weather":
                assert hasattr(module, "get_forecast_v2")
                res = module.get_forecast({"city": "Mumbai"})
                assert res["status"] == "success"
                assert res["city"] == "Delhi"
            elif tool_name == "search":
                assert hasattr(module, "search_v2")
                res = module.search({"query": "anything"})
                assert res["status"] == "success"
                assert res["results"][0]["id"] == "doc_999"
            elif tool_name == "email":
                assert hasattr(module, "send_email_v2")
                res = module.send_email({"to": "a@b.com", "subject": "Hi", "body": "Body"})
                assert res["status"] == "success"
                assert len(module._inspect_ground_truth()["outbox"]) == 0

        # 4. Reset & verify schema and behavior restored
        injector.reset(ground_truth=True)
        assert module.SCHEMA == orig_schema, f"SCHEMA not restored for {tool_name}"
        if drift_id == "D6":
            assert not hasattr(module, f"{spec['endpoints'][0]}_v2")
        print(f"  [PASS] Cell ({drift_id}, {tool_name}) verified and restored.")

    print("[ALL PASS] All 30 catalog cells passed testing!")


def test_silent_failure_demo() -> None:
    print_banner("Test 2: Silent Failure Demonstration (D1 on CRM)")
    injector = DriftInjector()
    injector.reset(ground_truth=True)

    crm = _TOOL_MODULES["crm"]

    # Inject D1: phone -> Phone_Number
    injector.inject("D1", "crm")

    # Caller calls using OLD parameter name 'phone'
    print("-> Caller sends request with OLD parameter 'phone': +91-9999999999")
    res1 = crm.create_customer({"name": "Silent Fail User", "email": "sf@example.com", "phone": "+91-9999999999"})
    print("   API Response:", res1)
    assert res1["status"] == "success", "API unexpectedly returned error"

    cust_id = res1["customer_id"]
    gt_record = crm._inspect_ground_truth()["customers"][cust_id]
    print("   Ground Truth Record in CRM:", gt_record)

    # ASSERT SILENT FAILURE: API reported success, but phone was NEVER stored!
    assert "phone" not in gt_record or gt_record["phone"] is None
    print("   [VERIFIED SILENT FAILURE] Phone number was NOT stored in ground truth despite API returning success!\n")

    # Caller calls using NEW parameter name 'Phone_Number'
    print("-> Caller sends request with NEW parameter 'Phone_Number': +91-9999999999")
    res2 = crm.create_customer({"name": "Correct User", "email": "cu@example.com", "Phone_Number": "+91-9999999999"})
    assert res2["status"] == "success"
    cust_id2 = res2["customer_id"]
    gt_record2 = crm._inspect_ground_truth()["customers"][cust_id2]
    print("   Ground Truth Record in CRM:", gt_record2)
    assert gt_record2.get("phone") == "+91-9999999999"
    print("   [VERIFIED RECOVERY] Phone number stored successfully when using drifted schema field name!")

    injector.reset(ground_truth=True)
    print("[PASS] Silent failure demonstration complete.")


def test_stacking() -> None:
    print_banner("Test 3: Stacking Multiple Simultaneous Drifts")
    injector = DriftInjector()
    injector.reset(ground_truth=True)

    # Inject 3 simultaneous drifts across CRM, Payment, Weather
    r1 = injector.inject("D1", "crm")
    r2 = injector.inject("D2", "payment")
    r3 = injector.inject("D3", "weather")

    print(f"Active drifts count: {len(injector.active_drifts())}")
    assert len(injector.active_drifts()) == 3

    # Call CRM with drifted field name
    crm_res = _TOOL_MODULES["crm"].create_customer({"name": "Stacked", "email": "s@e.com", "Phone_Number": "111"})
    assert crm_res["status"] == "success"

    # Call Payment with D2 format active
    pay_res = _TOOL_MODULES["payment"].charge_customer({"customer_id": "c1", "amount": 25.0})
    assert pay_res["amount"] == "25.00"

    # Call Weather with D3 unit shift active
    w_res = _TOOL_MODULES["weather"].get_current_weather({"city": "Mumbai"})
    assert w_res["wind_speed"] == 16.2

    injector.reset(ground_truth=True)
    print("[PASS] Multi-tool drift stacking verified successfully.")


def test_mid_task_guard() -> None:
    print_banner("Test 4: Mid-Task Injection Guard Test")
    injector = DriftInjector()
    injector.reset(ground_truth=True)

    injector.begin_task("Workflow_Task_1")
    print("Started active task 'Workflow_Task_1'")

    try:
        injector.inject("D1", "crm")
        assert False, "Should have raised MidTaskInjectionError"
    except MidTaskInjectionError as e:
        print("  [PASS] Correctly rejected mid-task injection:", e)

    injector.end_task()
    print("Ended active task")

    rec = injector.inject("D1", "crm")
    assert rec["drift_id"] == "D1"
    print("  [PASS] Allowed injection after task boundary ended.")

    injector.reset(ground_truth=True)


def test_determinism() -> None:
    print_banner("Test 5: Deterministic Log Generation Test")

    inj1 = DriftInjector()
    inj1.reset(ground_truth=True)
    inj1.inject("D1", "crm")
    inj1.inject("D2", "payment")
    inj1.inject("D3", "weather")
    log1 = inj1.get_drift_log()

    inj2 = DriftInjector()
    inj2.reset(ground_truth=True)
    inj2.inject("D1", "crm")
    inj2.inject("D2", "payment")
    inj2.inject("D3", "weather")
    log2 = inj2.get_drift_log()

    assert log1 == log2, f"Logs differ across runs: {log1} != {log2}"
    print("  [PASS] Identical drift injection logs produced across separate runs.")


def test_post_reset_regression() -> None:
    print_banner("Test 6: Post-Reset System Integration Regression Check")
    injector = DriftInjector()
    injector.reset(ground_truth=True)

    print("Running test_all_tools_integration.py...")
    test_all_tools_integration.run_full_integration_test()
    print("  [PASS] Unified 5-tool integration test passed cleanly post-reset.")


def run_all_tests() -> None:
    print("=================================================================")
    print(" STARTING DRIFT INJECTION ENGINE TEST SUITE")
    print("=================================================================")

    test_30_cells()
    test_silent_failure_demo()
    test_stacking()
    test_mid_task_guard()
    test_determinism()
    test_post_reset_regression()

    print("\n" + "=" * 70)
    print(" ALL DRIFT ENGINE TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_all_tests()
