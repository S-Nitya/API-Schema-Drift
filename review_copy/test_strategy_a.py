"""Test suite for Strategy A: Schema-Diff Caching.

Verifies:
1. No-drift baseline for all 5 tools (auto-prime on first sight, PROCEED on repeated calls, stable hash).
2. Hash determinism (dict order invariance, sensitive to real changes).
3. Full catalog sweep over all 30 cells (15 detected / 15 not detected matching schema_visible flag).
4. Stacked drifts across different tools (isolated independent detection).
5. Reset behaviour (Strategy A detects schema restoration upon injector reset and re-caches).
6. Mini end-to-end scripted stub agent (CRM D1, Payment D4, CRM D6 silent failure prevention).
7. Instrumentation counters and reset_stats validation (llm_calls == 0, total_check_ns > 0).

Style: Plain-script, stdlib only, assertions, exit code 0 on pass.
"""

import copy
import sys
import time
from typing import Any, Dict

from drift_engine.drift_injector import DRIFT_CATALOG, DriftInjector
from mitigation.base import Action, PreCallResult
from mitigation.strategy_a import SchemaDiffCaching, compute_schema_hash
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api

TOOLS = ["crm", "payment", "weather", "search", "email"]
SAMPLE_REQUESTS = {
    ("crm", "create_customer"): {"name": "Test User", "email": "test@example.com"},
    ("payment", "charge_customer"): {"customer_id": "cust_0001", "amount": 25.0},
    ("weather", "get_current_weather"): {"city": "Bengaluru"},
    ("search", "search"): {"query": "ticket policy"},
    ("email", "send_email"): {"to": "user@example.com", "subject": "Hi", "body": "Hello"},
}


def test_1_no_drift_baseline() -> None:
    print("\n" + "=" * 70)
    print("Test 1: No-Drift Baseline (All 5 Tools)")
    print("=" * 70)

    injector = DriftInjector()
    injector.reset(ground_truth=True)
    strategy = SchemaDiffCaching()

    for tool in TOOLS:
        # 1. First call: primes the cache and returns PROCEED
        endpoint = list(injector._tools[tool].SCHEMA["endpoints"].keys())[0]
        sample_req = SAMPLE_REQUESTS.get((tool, endpoint), {})

        res1 = strategy.pre_call(tool, endpoint, sample_req)
        assert res1.action == Action.PROCEED, f"First call on {tool} must PROCEED"
        assert res1.drift_detected is False, f"First call on {tool} must not flag drift"
        assert res1.old_hash is None, f"First call on {tool} must have old_hash=None"
        assert res1.new_hash is not None, f"First call on {tool} must compute new_hash"
        assert res1.schema is not None, f"First call on {tool} must return live schema snapshot"
        assert res1.diff is None, f"First call on {tool} must have diff=None"

        prime_hash = res1.new_hash

        # 2. Repeated calls: zero false positives, hash remains identical
        for i in range(5):
            res_rep = strategy.pre_call(tool, endpoint, sample_req)
            assert res_rep.action == Action.PROCEED, f"Call {i+2} on {tool} must PROCEED"
            assert res_rep.drift_detected is False, f"Call {i+2} on {tool} must not flag drift"
            assert res_rep.old_hash == prime_hash, f"Hash changed unexpectedly on {tool}"
            assert res_rep.new_hash == prime_hash, f"Hash changed unexpectedly on {tool}"
            assert res_rep.diff is None, f"Call {i+2} on {tool} must have diff=None"

        print(f"  [PASS] Tool '{tool}': auto-primed (hash: {prime_hash[:12]}...), 5/5 repeated calls PROCEED.")

    assert strategy.stats["drifts_detected"] == 0
    assert strategy.stats["reloads_triggered"] == 0
    print("[PASS] Test 1 completed successfully with zero false positives.")


def test_2_hash_determinism() -> None:
    print("\n" + "=" * 70)
    print("Test 2: Hash Determinism & Sensitivity")
    print("=" * 70)

    schema_a = {
        "tool": "test",
        "endpoints": {
            "ep1": {
                "request": {
                    "field_b": {"type": int, "required": False},
                    "field_a": {"type": str, "required": True},
                },
                "response": {"status": {"type": str}},
            }
        },
    }

    # Reverse dictionary key orders at all levels
    schema_b = {
        "endpoints": {
            "ep1": {
                "response": {"status": {"type": str}},
                "request": {
                    "field_a": {"type": str, "required": True},
                    "field_b": {"type": int, "required": False},
                },
            }
        },
        "tool": "test",
    }

    hash_a = compute_schema_hash(schema_a)
    hash_b = compute_schema_hash(schema_b)
    assert hash_a == hash_b, "Hash must be invariant to dict key ordering!"
    print(f"  [PASS] Key-order invariance verified: {hash_a[:16]}... == {hash_b[:16]}...")

    # Real change 1: type change
    schema_c = copy.deepcopy(schema_a)
    schema_c["endpoints"]["ep1"]["request"]["field_a"]["type"] = int
    hash_c = compute_schema_hash(schema_c)
    assert hash_c != hash_a, "Hash must change when field type changes"

    # Real change 2: required flip
    schema_d = copy.deepcopy(schema_a)
    schema_d["endpoints"]["ep1"]["request"]["field_b"]["required"] = True
    hash_d = compute_schema_hash(schema_d)
    assert hash_d != hash_a, "Hash must change when required flag flips"

    # Real change 3: field rename
    schema_e = copy.deepcopy(schema_a)
    schema_e["endpoints"]["ep1"]["request"]["field_c"] = schema_e["endpoints"]["ep1"]["request"].pop("field_b")
    hash_e = compute_schema_hash(schema_e)
    assert hash_e != hash_a, "Hash must change when field is renamed"

    print("  [PASS] Hash sensitivity verified across type change, required flip, and field rename.")
    print("[PASS] Test 2 completed successfully.")


def test_3_full_catalog_sweep_30_cells() -> None:
    print("\n" + "=" * 70)
    print("Test 3: Full 30-Cell Catalog Sweep (D1-D6 x 5 Tools)")
    print("=" * 70)

    injector = DriftInjector()
    detected_count = 0
    not_detected_count = 0

    detected_cells = []
    not_detected_cells = []

    # Sort catalog keys deterministically: D1-D6, then tool
    catalog_keys = sorted(DRIFT_CATALOG.keys(), key=lambda k: (k[0], k[1]))

    for drift_id, tool in catalog_keys:
        injector.reset(ground_truth=True)
        spec = DRIFT_CATALOG[(drift_id, tool)]
        is_schema_visible = spec["schema_visible"]

        # Strategy instance fresh and primed on baseline schema
        strategy = SchemaDiffCaching()
        prime_hash = strategy.prime(tool)

        # Inject drift
        injector.inject(drift_id, tool)

        # Trigger pre_call
        ep = spec["endpoints"][0]
        sample_req = SAMPLE_REQUESTS.get((tool, ep), {})
        res = strategy.pre_call(tool, ep, sample_req)

        if is_schema_visible:
            assert res.drift_detected is True, (
                f"Cell ({drift_id}, {tool}) is marked schema_visible=True, but was NOT detected!"
            )
            assert res.action == Action.RELOAD_SCHEMA, (
                f"Cell ({drift_id}, {tool}) must return RELOAD_SCHEMA"
            )
            assert res.old_hash == prime_hash, f"old_hash mismatch on ({drift_id}, {tool})"
            assert res.new_hash != prime_hash, f"new_hash must differ on ({drift_id}, {tool})"
            assert res.diff is not None, f"diff must be present on ({drift_id}, {tool})"
            assert res.reload_message is not None and len(res.reload_message) > 0, (
                f"reload_message must be non-empty on ({drift_id}, {tool})"
            )

            # Assert cache was updated: a second call immediately returns PROCEED
            res2 = strategy.pre_call(tool, ep, sample_req)
            assert res2.action == Action.PROCEED, (
                f"Cell ({drift_id}, {tool}) second call must PROCEED after cache update"
            )
            assert res2.drift_detected is False, (
                f"Cell ({drift_id}, {tool}) second call must not re-flag drift"
            )

            detected_count += 1
            detected_cells.append(f"({drift_id}, {tool})")
        else:
            assert res.drift_detected is False, (
                f"Cell ({drift_id}, {tool}) is marked schema_visible=False, but was detected!"
            )
            assert res.action == Action.PROCEED, (
                f"Cell ({drift_id}, {tool}) must PROCEED"
            )
            assert res.diff is None, f"Cell ({drift_id}, {tool}) must have diff=None"
            not_detected_count += 1
            not_detected_cells.append(f"({drift_id}, {tool})")

    injector.reset(ground_truth=True)

    print(f"Detected Cells ({detected_count}/30): {', '.join(detected_cells)}")
    print(f"Not Detected Cells ({not_detected_count}/30): {', '.join(not_detected_cells)}")

    assert detected_count == 15, f"Expected exactly 15 detected cells (D1, D4, D6), got {detected_count}"
    assert not_detected_count == 15, f"Expected exactly 15 not-detected cells (D2, D3, D5), got {not_detected_count}"
    print("[PASS] Test 3 catalog sweep complete: 15/15 detected/not-detected exact split verified.")


def test_4_stacked_drifts_across_tools() -> None:
    print("\n" + "=" * 70)
    print("Test 4: Stacked Drifts Across Different Tools")
    print("=" * 70)

    injector = DriftInjector()
    injector.reset(ground_truth=True)

    strategy = SchemaDiffCaching()
    strategy.prime("crm")
    strategy.prime("payment")
    strategy.prime("weather")

    # Inject D1 on CRM and D4 on Payment; Weather remains clean
    injector.inject("D1", "crm")
    injector.inject("D4", "payment")

    # 1. CRM call: flags D1
    res_crm = strategy.pre_call("crm", "create_customer", {"name": "Bob", "email": "bob@example.com"})
    assert res_crm.action == Action.RELOAD_SCHEMA
    assert res_crm.drift_detected is True
    assert "Phone_Number" in res_crm.reload_message

    # 2. Weather call: un-drifted, PROCEED
    res_w = strategy.pre_call("weather", "get_current_weather", {"city": "Delhi"})
    assert res_w.action == Action.PROCEED
    assert res_w.drift_detected is False

    # 3. Payment call: flags D4
    res_pay = strategy.pre_call("payment", "charge_customer", {"customer_id": "cust_0001", "amount": 10.0})
    assert res_pay.action == Action.RELOAD_SCHEMA
    assert res_pay.drift_detected is True
    assert "payment_method" in res_pay.reload_message

    # 4. Subsequent calls on CRM and Payment PROCEED (caches updated)
    res_crm_2 = strategy.pre_call("crm", "create_customer", {"name": "Bob", "email": "bob@example.com"})
    assert res_crm_2.action == Action.PROCEED

    res_pay_2 = strategy.pre_call("payment", "charge_customer", {"customer_id": "cust_0001", "amount": 10.0})
    assert res_pay_2.action == Action.PROCEED

    injector.reset(ground_truth=True)
    print("  [PASS] Multi-tool stacked drifts detected independently without cross-talk.")
    print("[PASS] Test 4 completed successfully.")


def test_5_reset_behaviour() -> None:
    print("\n" + "=" * 70)
    print("Test 5: Reset Behaviour & Schema Reversion Detection")
    print("=" * 70)

    injector = DriftInjector()
    injector.reset(ground_truth=True)

    strategy = SchemaDiffCaching()
    h_clean = strategy.prime("crm")

    # Inject D1 on CRM
    injector.inject("D1", "crm")
    res_drift = strategy.pre_call("crm", "create_customer", {})
    assert res_drift.action == Action.RELOAD_SCHEMA
    h_drifted = res_drift.new_hash
    assert h_clean != h_drifted

    # Second call under drift: PROCEED (cached)
    res_drift_repeat = strategy.pre_call("crm", "create_customer", {})
    assert res_drift_repeat.action == Action.PROCEED

    # Now reset injector: restores original clean schema
    injector.reset(ground_truth=True)

    # Next call through Strategy A:
    # Live schema is now clean S0, but Strategy A has cached drifted S1.
    # It must detect the reversion mismatch, trigger RELOAD_SCHEMA, and re-cache clean S0!
    res_revert = strategy.pre_call("crm", "create_customer", {})
    assert res_revert.action == Action.RELOAD_SCHEMA, (
        "Strategy A must detect schema reversion upon injector reset as a schema change"
    )
    assert res_revert.drift_detected is True
    assert res_revert.old_hash == h_drifted
    assert res_revert.new_hash == h_clean

    # Subsequent call proceeds cleanly
    res_clean_repeat = strategy.pre_call("crm", "create_customer", {})
    assert res_clean_repeat.action == Action.PROCEED
    assert res_clean_repeat.drift_detected is False

    print("  [PASS] Verified: Reversion to original schema is detected, flagged, and re-cached.")
    print("[PASS] Test 5 completed successfully.")


def test_6_mini_end_to_end_stub_agent() -> None:
    print("\n" + "=" * 70)
    print("Test 6: Mini End-to-End with Scripted Stub Agent")
    print("=" * 70)

    injector = DriftInjector()

    # -------------------------------------------------------------------------
    # Case A: CRM D1 (phone -> Phone_Number)
    # -------------------------------------------------------------------------
    print("--> Case A: CRM D1 (Field Rename 'phone' -> 'Phone_Number')")
    injector.reset(ground_truth=True)
    injector.inject("D1", "crm")

    # 1. Run WITHOUT Strategy A (Baseline / Unmitigated agent)
    unmit_req = {
        "name": "Alice Unmitigated",
        "email": "alice_unmit@example.com",
        "phone": "+91-9876543210",
    }
    unmit_res = crm_api.create_customer(unmit_req)
    assert unmit_res["status"] == "success"
    unmit_cid = unmit_res["customer_id"]

    gt_unmit = crm_api._inspect_ground_truth()["customers"][unmit_cid]
    assert "phone" not in gt_unmit, (
        "SILENT FAILURE VERIFICATION: Unmitigated call must drop 'phone' from ground truth!"
    )
    print(f"  [SILENT FAILURE OBSERVED] Customer {unmit_cid} created without phone in ground truth.")

    # 2. Run WITH Strategy A (Stub agent rebuilds request on RELOAD_SCHEMA)
    # Re-reset and re-inject to isolate test
    injector.reset(ground_truth=True)
    strategy_a = SchemaDiffCaching()
    strategy_a.prime("crm")  # Agent initially read baseline schema

    injector.inject("D1", "crm")  # Drift injected between tasks

    initial_req = {
        "name": "Alice Mitigated",
        "email": "alice_mit@example.com",
        "phone": "+91-9876543210",
    }

    # Pre-call check
    pre_result = strategy_a.pre_call("crm", "create_customer", initial_req)
    assert pre_result.action == Action.RELOAD_SCHEMA
    assert pre_result.drift_detected is True

    # Scripted stub agent request-rebuilder:
    # Agent checks diff candidate renames or live schema
    rebuilt_req = dict(initial_req)
    if pre_result.diff and "create_customer" in pre_result.diff.get("endpoint_changes", {}):
        chgs = pre_result.diff["endpoint_changes"]["create_customer"]
        for r in chgs.get("renamed_candidates", []):
            if r["old_field"] in rebuilt_req:
                val = rebuilt_req.pop(r["old_field"])
                rebuilt_req[r["new_field"]] = val

    assert "Phone_Number" in rebuilt_req
    assert "phone" not in rebuilt_req

    # Dispatch rebuilt request
    mit_res = crm_api.create_customer(rebuilt_req)
    assert mit_res["status"] == "success"
    mit_cid = mit_res["customer_id"]

    gt_mit = crm_api._inspect_ground_truth()["customers"][mit_cid]
    assert gt_mit.get("phone") == "+91-9876543210", (
        "RECOVERY VERIFICATION: Phone number must be properly preserved in ground truth!"
    )
    print(f"  [RECOVERY VERIFIED] Customer {mit_cid} stored with phone '{gt_mit['phone']}' in ground truth.")

    # -------------------------------------------------------------------------
    # Case B: Payment D4 (payment_method string -> dict)
    # -------------------------------------------------------------------------
    print("\n--> Case B: Payment D4 (Nested Structure Change 'payment_method')")
    injector.reset(ground_truth=True)

    # 1. Run WITHOUT Strategy A
    injector.inject("D4", "payment")
    flat_charge_req = {
        "customer_id": "cust_0001",
        "amount": 50.0,
        "payment_method": "card",
    }
    unmit_pay_res = payment_api.charge_customer(flat_charge_req)
    assert unmit_pay_res["status"] == "error", "Without mitigation, flat payment_method should fail validation"
    print("  [FAILURE OBSERVED] Unmitigated call rejected due to structural schema mismatch.")

    # 2. Run WITH Strategy A
    injector.reset(ground_truth=True)
    strategy_a = SchemaDiffCaching()
    strategy_a.prime("payment")

    injector.inject("D4", "payment")
    pre_pay = strategy_a.pre_call("payment", "charge_customer", flat_charge_req)
    assert pre_pay.action == Action.RELOAD_SCHEMA
    assert pre_pay.drift_detected is True

    # Stub agent rebuilds payment_method as nested dict matching new schema
    rebuilt_pay_req = dict(flat_charge_req)
    rebuilt_pay_req["payment_method"] = {"type": "card", "details": "Visa ending in 4242"}

    mit_pay_res = payment_api.charge_customer(rebuilt_pay_req)
    assert mit_pay_res["status"] == "success"
    tx_id = mit_pay_res["transaction_id"]
    gt_tx = payment_api._inspect_ground_truth()["transactions"][tx_id]
    assert gt_tx["amount"] == 50.0
    print(f"  [RECOVERY VERIFIED] Charge succeeded (tx: {tx_id}) using rebuilt nested payload.")

    # -------------------------------------------------------------------------
    # Case C: CRM D6 (Endpoint Deprecation get_customer -> get_customer_v2)
    # -------------------------------------------------------------------------
    print("\n--> Case C: CRM D6 (Endpoint Deprecation 'get_customer' -> 'get_customer_v2')")
    injector.reset(ground_truth=True)

    # Seed genuine customer
    seed_res = crm_api.create_customer({"name": "Charlie Real", "email": "charlie@example.com"})
    charlie_id = seed_res["customer_id"]

    # 1. Run WITHOUT Strategy A
    injector.inject("D6", "crm")
    fallback_res = crm_api.get_customer({"customer_id": charlie_id})
    assert fallback_res["status"] == "success"
    # D6 returns dummy fallback data, not real customer record!
    assert fallback_res["customer"]["name"] == "Placeholder Customer"
    print(f"  [SILENT FAILURE OBSERVED] Old endpoint returned dummy placeholder name '{fallback_res['customer']['name']}'.")

    # 2. Run WITH Strategy A
    injector.reset(ground_truth=True)
    seed_res2 = crm_api.create_customer({"name": "Charlie Real", "email": "charlie@example.com"})
    charlie_id2 = seed_res2["customer_id"]

    strategy_a = SchemaDiffCaching()
    strategy_a.prime("crm")

    injector.inject("D6", "crm")

    pre_d6 = strategy_a.pre_call("crm", "get_customer", {"customer_id": charlie_id2})
    assert pre_d6.action == Action.RELOAD_SCHEMA
    assert pre_d6.drift_detected is True
    assert len(pre_d6.diff["endpoints_deprecated"]) > 0
    assert pre_d6.diff["endpoints_deprecated"][0]["replaced_by"] == "get_customer_v2"

    # Stub agent switches target endpoint based on deprecation metadata
    replacement_ep = pre_d6.diff["endpoints_deprecated"][0]["replaced_by"]
    handler = getattr(crm_api, replacement_ep)
    mit_get_res = handler({"customer_id": charlie_id2})

    assert mit_get_res["status"] == "success"
    assert mit_get_res["customer"]["name"] == "Charlie Real"
    print(f"  [RECOVERY VERIFIED] Successfully redirected to '{replacement_ep}', retrieved real record '{mit_get_res['customer']['name']}'.")

    injector.reset(ground_truth=True)
    print("[PASS] Test 6 mini end-to-end completed successfully across D1, D4, and D6.")


def test_7_stats_instrumentation() -> None:
    print("\n" + "=" * 70)
    print("Test 7: Instrumentation Stats & Performance Counter")
    print("=" * 70)

    injector = DriftInjector()
    injector.reset(ground_truth=True)

    strategy = SchemaDiffCaching()

    # Initial stats should all be 0
    init_stats = strategy.stats
    assert init_stats["schema_fetches"] == 0
    assert init_stats["hash_comparisons"] == 0
    assert init_stats["drifts_detected"] == 0
    assert init_stats["reloads_triggered"] == 0
    assert init_stats["llm_calls"] == 0
    assert init_stats["total_check_ns"] == 0

    # Prime CRM
    strategy.prime("crm")
    assert strategy.stats["schema_fetches"] == 1
    assert strategy.stats["total_check_ns"] > 0

    # Repeated call without drift
    strategy.pre_call("crm", "create_customer", {})
    assert strategy.stats["schema_fetches"] == 2
    assert strategy.stats["hash_comparisons"] == 1
    assert strategy.stats["drifts_detected"] == 0
    assert strategy.stats["reloads_triggered"] == 0

    # Inject drift and call
    injector.inject("D1", "crm")
    strategy.pre_call("crm", "create_customer", {})
    assert strategy.stats["schema_fetches"] == 3
    assert strategy.stats["hash_comparisons"] == 2
    assert strategy.stats["drifts_detected"] == 1
    assert strategy.stats["reloads_triggered"] == 1
    assert strategy.stats["llm_calls"] == 0
    assert strategy.stats["total_check_ns"] > 0

    print(f"  [PASS] Measured stats: {strategy.stats}")

    # Test reset_stats
    strategy.reset_stats()
    reset_stats = strategy.stats
    assert reset_stats["schema_fetches"] == 0
    assert reset_stats["hash_comparisons"] == 0
    assert reset_stats["drifts_detected"] == 0
    assert reset_stats["reloads_triggered"] == 0
    assert reset_stats["llm_calls"] == 0
    assert reset_stats["total_check_ns"] == 0
    print("  [PASS] reset_stats() correctly zeroed all counters.")

    injector.reset(ground_truth=True)
    print("[PASS] Test 7 completed successfully.")


if __name__ == "__main__":
    t_start = time.perf_counter()
    print("Starting Strategy A (Schema-Diff Caching) Verification Suite")

    test_1_no_drift_baseline()
    test_2_hash_determinism()
    test_3_full_catalog_sweep_30_cells()
    test_4_stacked_drifts_across_tools()
    test_5_reset_behaviour()
    test_6_mini_end_to_end_stub_agent()
    test_7_stats_instrumentation()

    t_elapsed = time.perf_counter() - t_start
    print("\n" + "=" * 70)
    print(f"ALL STRATEGY A TESTS PASSED SUCCESSFULLY in {t_elapsed:.3f}s!")
    print("=" * 70)
    sys.exit(0)
