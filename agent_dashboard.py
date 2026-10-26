import copy
import json
import pandas as pd
import streamlit as st
from typing import Any, Dict, List, Optional

from contracts import Action, NoOpMitigation, PreCallResult
from agent.agent_loop import Agent, RunResult, StepResult
from agent.planner import ScriptedPlanner, Plan, PlanStep
from agent.request_builder import ScriptedRequestBuilder
from agent.tool_caller import ToolCaller
from agent.event_log import EventLog
from agent.schema_memory import SchemaMemory, jsonable
from drift_engine.drift_injector import DriftInjector, DRIFT_CATALOG

class W01ScriptedPlanner(ScriptedPlanner):
    def __init__(self):
        super().__init__(steps=[PlanStep(step_id="init", tool="crm", endpoint="create_customer", intent="init")])

    def plan(self, task: str, catalog: Dict) -> Plan:
        # Exact 3-step plan for Workflow 01
        return Plan(
            steps=[
                PlanStep(step_id="s1", tool="crm", endpoint="create_customer", intent="Onboard customer"),
                PlanStep(step_id="s2", tool="payment", endpoint="charge_customer", intent="Charge setup fee"),
                PlanStep(step_id="s3", tool="email", endpoint="send_email", intent="Send receipt"),
            ]
        )

class W01ScriptedRequestBuilder(ScriptedRequestBuilder):
    def __init__(self, step_responses: Optional[Dict] = None):
        super().__init__(step_responses=step_responses or {})

    def build(self, task: str, step: PlanStep, req_schema: Dict, context: Dict, hints: Optional[Dict] = None) -> Dict:
        if step.step_id == "s1":
            return {"name": "Acme Corp", "email": "billing@acme.com", "phone": "+1-555-0199", "company": "Acme Corporation", "status": "active", "address": {"street": "100 Innovation Way", "city": "Bengaluru", "country": "IN", "postal_code": "560001"}}
        elif step.step_id == "s2":
            cid = context.get("s1", {}).get("customer_id", "unknown")
            return {"customer_id": cid, "amount": 500.0, "currency": "USD", "description": "Enterprise Onboarding Setup Fee", "payment_method": "card"}
        elif step.step_id == "s3":
            cid = context.get("s1", {}).get("customer_id", "unknown")
            txid = context.get("s2", {}).get("transaction_id", "unknown")
            return {"to": "billing@acme.com", "subject": "Welcome to Enterprise Sponsorship - Invoice Receipt", "body": f"Hello Acme Corp, your account ({cid}) is active. We successfully processed your setup fee of USD 500.00 (Tx: {txid}).", "cc": ["finance@acme.com"], "sender": {"email": "accounts@events.org", "name": "Event Accounts Desk"}}
        return {}

def get_tool_ground_truth() -> Dict:
    import mock_tools.crm_api as crm_api
    import mock_tools.payment_api as payment_api
    import mock_tools.email_api as email_api
    return {"crm": crm_api._inspect_ground_truth(), "payment": payment_api._inspect_ground_truth(), "email": email_api._inspect_ground_truth()}

def run_scenario(drift_id: Optional[str], tool: Optional[str], strategy_name: str = "baseline", injector: Optional[DriftInjector] = None) -> Dict:
    if injector is None: injector = DriftInjector()
    injector.reset(ground_truth=True)
    strategy = NoOpMitigation()
    agent = Agent(planner=W01ScriptedPlanner(), builder=W01ScriptedRequestBuilder(), strategy=strategy, caller=ToolCaller(), memory=SchemaMemory(), log=EventLog(), injector=injector)
    agent.read_schemas(["crm", "payment", "email"])
    snapshot_schema = copy.deepcopy(agent.memory.catalog())
    live_schema_after_drift = None
    if drift_id and tool:
        injector.inject(drift_id, tool)
        import mock_tools.crm_api as crm_api
        import mock_tools.payment_api as payment_api
        import mock_tools.email_api as email_api
        tool_mods = {"crm": crm_api, "payment": payment_api, "email": email_api}
        live_schema_after_drift = {t: tool_mods[t].SCHEMA for t in ["crm", "payment", "email"]}
    try:
        result = agent.run_task("Onboard Acme Corp and send the setup-fee receipt.")
        gt = get_tool_ground_truth()
        lost_values = []
        for step in result.steps:
            req, tool_id = step.request, step.tool
            tool_gt = gt.get(tool_id, {})
            sent_values = []
            def flatten(d):
                if isinstance(d, dict):
                    for v in d.values(): flatten(v)
                elif isinstance(d, list):
                    for v in d: flatten(v)
                else: sent_values.append(str(d))
            flatten(req)
            gt_string = json.dumps(tool_gt)
            for val in sent_values:
                if val not in gt_string: lost_values.append(f"Step {step.step_id} ({tool_id}): value '{val}' not found in ground truth")
        return {"result": result, "events": agent.log.all(), "snapshot_schema": jsonable(snapshot_schema), "live_schema_after_drift": jsonable(live_schema_after_drift), "ground_truth": gt, "drift_info": injector.get_drift_log()[-1] if injector.get_drift_log() else None, "strategy_name": strategy_name, "lost_values": lost_values}
    finally:
        injector.reset(ground_truth=True)

def render_agent_tab():
    st.subheader("Agent Loop Execution Trace")
    st.caption("Run a scripted version of Workflow 01 (CRM -> Payment -> Email) to observe the agent's behavior.")
    if "injector" not in st.session_state: st.session_state.injector = DriftInjector()
    injector = st.session_state.injector
    col1, col2, col3 = st.columns(3)
    with col1:
        drift_options = ["None (clean run)"] + [f"{did} {tool}: {spec['drift_name']}" for (did, tool), spec in DRIFT_CATALOG.items() if tool in ["crm", "payment", "email"]]
        selected_drift_opt = st.selectbox("Select Drift Scenario", options=drift_options, key="agent_drift_sel")
    with col2:
        strategy_sel = st.selectbox("Strategy", options=["baseline"], key="agent_strat_sel")
    with col3:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("Run Agent", type="primary", width="stretch")
    if run_btn:
        with st.spinner("Agent executing task..."):
            did, tool = (None, None) if selected_drift_opt == "None (clean run)" else (selected_drift_opt.split(" ")[0], selected_drift_opt.split(" ")[1])
            res = run_scenario(did, tool, strategy_sel, injector=injector)
            st.session_state["agent_tab_last_run"] = res
        st.rerun()
    last_run = st.session_state.get("agent_tab_last_run")
    if not last_run:
        st.info("Select a scenario and click 'Run Agent' to see the loop in action.")
        return
    result, lost = last_run["result"], last_run["lost_values"]
    if result.status == "completed" and not lost: st.success("✅ RUN SUCCESSFUL: Task completed and all data preserved in ground truth.")
    elif result.status == "completed" and lost: st.error("🚨 SILENT FAILURE: Agent reported success, but data was lost during API calls!")
    elif result.status == "halted": st.warning(f"⚠️ RUN HALTED: {result.reason}")
    else: st.error(f"❌ RUN FAILED: {result.reason}")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Status", result.status); m2.metric("Reported Success", str(result.reported_success)); m3.metric("Steps Run", len(result.steps)); m4.metric("Tool Calls", result.tool_calls); m5.metric("Elapsed (s)", f"{result.elapsed_s:.2f}")
    st.divider()
    st.markdown("### 1. Schema the agent knows vs what the API is now")
    col_snap, col_live = st.columns(2)
    with col_snap: st.markdown("**Agent's Snapshot (T=0)**"); st.json(last_run["snapshot_schema"])
    with col_live:
        st.markdown("**Live API Schema (After Drift)**")
        st.json(last_run["live_schema_after_drift"]) if last_run["live_schema_after_drift"] else st.info("No drift injected. Live schema matches snapshot.")
    st.markdown("### 2. Step Timeline")
    for step in result.steps:
        status_icon = "✅" if step.status == "ok" else "❌"
        with st.expander(f"{status_icon} Step {step.step_id}: {step.tool}.{step.endpoint}", expanded=True):
            c1, c2 = st.columns(2)
            with c1: st.markdown("**Request Sent**"); st.json(step.request)
            with c2: st.markdown("**Response Received**"); st.json(step.response)
            step_events = [e for e in last_run["events"] if e.get("step_id") == step.step_id]
            pre_act = next((e["action"] for e in step_events if e["kind"] == "pre_call"), "N/A")
            post_act = next((e["action"] for e in step_events if e["kind"] == "post_call"), "N/A")
            st.caption(f"Pre-call action: {pre_act} | Post-call action: {post_act}")
    st.markdown("### 3. Ground Truth Inspection")
    gt = last_run["ground_truth"]
    for tool_id, state in gt.items():
        with st.expander(f"{tool_id.upper()} Final State"): st.json(state)
    if lost:
        st.warning("**Lost Values Heuristic:**")
        for l in lost: st.markdown(f"- {l}")
    st.markdown("### 4. Event Log")
    df = pd.DataFrame(last_run["events"])
    if not df.empty:
        st.dataframe(df[["seq", "kind", "timestamp"]], width="stretch", hide_index=True)
        with st.expander("View Full Event JSON"): st.json(last_run["events"])
    st.caption("Note: This tab resets the global drift state before and after each run to ensure a clean start.")
