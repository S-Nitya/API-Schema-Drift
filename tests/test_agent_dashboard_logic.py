import pytest
from agent_dashboard import run_scenario, get_tool_ground_truth
from drift_engine.drift_injector import DriftInjector

def test_clean_run():
    injector = DriftInjector()
    res = run_scenario(None, None, "baseline", injector=injector)
    
    assert res["result"].status == "completed"
    assert res["result"].reported_success is True
    assert len(res["lost_values"]) == 0
    
    # Check ground truth populated (simplified check)
    gt = res["ground_truth"]
    assert len(gt["crm"]["customers"]) > 0
    assert len(gt["payment"]["transactions"]) > 0
    assert len(gt["email"]["outbox"]) > 0

def test_d1_silent_failure():
    injector = DriftInjector()
    # D1 on CRM: phone -> Phone_Number
    res = run_scenario("D1", "crm", "baseline", injector=injector)

    # Baseline agent reports success but loses the phone field
    assert res["result"].status == "completed"
    assert res["result"].reported_success is True
    assert len(res["lost_values"]) > 0

    # Verify schema diff
    snap = res["snapshot_schema"]["crm"]["create_customer"]
    live = res["live_schema_after_drift"]["crm"]["endpoints"]["create_customer"]["request"]
    assert "phone" in snap
    assert "Phone_Number" in live
    assert "phone" not in live

def test_state_hygiene():
    injector = DriftInjector()
    # Run a drifted scenario
    run_scenario("D1", "crm", "baseline", injector=injector)
    
    # The logic should have reset the injector. Verify by checking active drifts
    assert len(injector.active_drifts()) == 0
    
    # Run a clean scenario immediately after
    res = run_scenario(None, None, "baseline", injector=injector)
    assert res["result"].status == "completed"
    assert len(res["lost_values"]) == 0

