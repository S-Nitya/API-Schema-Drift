"""Streamlit Dashboard for API Schema Drift Project Exploration.

A team-facing verification and exploration dashboard to inspect:
- Tab 1: Mock Tools Explorer (live handler execution & ground-truth inspection)
- Tab 2: Drift Engine Playground (before vs after drift injection & reset)
- Tab 3: Workflow Runner (step-by-step 12-workflow execution & ground-truth verification)
"""

import copy
import json
from typing import Any, Dict

import streamlit as st

import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api
from drift_engine.drift_injector import DRIFT_CATALOG, DriftInjector
from workflows import ALL_WORKFLOWS, WORKFLOW_REGISTRY

# Page configuration
st.set_page_config(
    page_title="API Schema Drift Explorer",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Global State & Injector Initialization
# -----------------------------------------------------------------------------
if "injector" not in st.session_state:
    st.session_state.injector = DriftInjector()

injector: DriftInjector = st.session_state.injector

# Tool mappings
TOOLS = {
    "CRM": {
        "id": "crm",
        "module": crm_api,
        "description": "Customer management (Salesforce / HubSpot style)",
    },
    "Payment": {
        "id": "payment",
        "module": payment_api,
        "description": "Charges, refunds, and ledger records (Stripe style)",
    },
    "Weather": {
        "id": "weather",
        "module": weather_api,
        "description": "Current conditions, multi-day forecasts, and alerts (OpenWeatherMap style)",
    },
    "Search": {
        "id": "search",
        "module": search_api,
        "description": "Corpus query search, document retrieval, and relevance scoring (Elasticsearch style)",
    },
    "Email": {
        "id": "email",
        "module": email_api,
        "description": "Message dispatch, delivery verification, and outbox logs (SendGrid style)",
    },
}

# Default sample values for form fields across endpoints
FIELD_DEFAULTS = {
    "name": "Alice Smith",
    "email": "alice.smith@acme.com",
    "phone": "+1-555-0199",
    "company": "Acme Corporation",
    "status": "active",
    "customer_id": "cust_0001",
    "amount": 50.0,
    "currency": "USD",
    "description": "Monthly Platform Subscription",
    "payment_method": "card",
    "transaction_id": "tx_0001",
    "reason": "requested_by_customer",
    "city": "Mumbai",
    "country_code": "IN",
    "days": 3,
    "query": "outdoor event safety",
    "max_results": 5,
    "page": 1,
    "document_id": "doc_001",
    "to": "attendee@example.com",
    "subject": "Important Event Update & Receipt",
    "body": "Your registration has been confirmed. Thank you!",
    "limit": 10,
    "address": {
        "street": "100 Innovation Way",
        "city": "Bengaluru",
        "country": "IN",
        "postal_code": "560001",
    },
    "metadata": {
        "tier": "enterprise",
        "annual_revenue": 50000.0,
    },
    "sender": {
        "email": "notifications@platform.io",
        "name": "Event Ops Desk",
    },
    "filters": {
        "category": "guidelines",
    },
    "cc": ["finance@acme.com"],
}

# Drift taxonomy descriptors
DRIFT_DESCRIPTIONS = {
    "D1": "D1 — Request Field Rename (e.g., phone -> Phone_Number)",
    "D2": "D2 — Response Format/Type Change (e.g., epoch timestamp -> ISO-8601, float -> string)",
    "D3": "D3 — Value Meaning/Unit Change (e.g., dollars -> cents, m/s -> km/h)",
    "D4": "D4 — Nested <-> Flat Structure Change (e.g., address dict <-> address_* fields)",
    "D5": "D5 — Silent Null Response (e.g., email or transaction_id becomes null)",
    "D6": "D6 — Endpoint Deprecation with Fallback Data (e.g., static placeholder returned)",
}

SAMPLE_PLAYGROUND_REQUESTS = {
    ("D1", "crm"): {"name": "Rahul Verma", "email": "rahul@example.com", "phone": "+91-9876543210"},
    ("D2", "crm"): {"name": "Rahul Verma", "email": "rahul@example.com"},
    ("D3", "crm"): {"name": "Rahul Verma", "email": "rahul@example.com", "metadata": {"annual_revenue": 500000.0}},
    ("D4", "crm"): {"name": "Rahul Verma", "email": "rahul@example.com", "address": {"street": "MG Road", "city": "Bengaluru", "country": "IN", "postal_code": "560001"}},
    ("D5", "crm"): {"customer_id": "cust_0001"},
    ("D6", "crm"): {"customer_id": "cust_0001"},

    ("D1", "payment"): {"customer_id": "cust_0001", "amount": 25.0, "currency": "USD", "description": "Standard Plan"},
    ("D2", "payment"): {"customer_id": "cust_0001", "amount": 50.0, "currency": "USD"},
    ("D3", "payment"): {"customer_id": "cust_0001", "amount": 4.0, "currency": "USD", "description": "Small Coffee"},
    ("D4", "payment"): {"customer_id": "cust_0001", "amount": 75.0, "payment_method": "card"},
    ("D5", "payment"): {"customer_id": "cust_0001", "amount": 100.0},
    ("D6", "payment"): {"transaction_id": "tx_0001", "amount": 50.0},

    ("D1", "weather"): {"city": "Mumbai", "country_code": "IN"},
    ("D2", "weather"): {"city": "Mumbai"},
    ("D3", "weather"): {"city": "Mumbai"},
    ("D4", "weather"): {"city": "Mumbai", "country_code": "IN"},
    ("D5", "weather"): {"city": "Mumbai"},
    ("D6", "weather"): {"city": "Mumbai", "days": 2},

    ("D1", "search"): {"query": "weather guidelines", "max_results": 3},
    ("D2", "search"): {"query": "safety policy"},
    ("D3", "search"): {"query": "safety policy"},
    ("D4", "search"): {"query": "guidelines", "filters": {"category": "guidelines"}},
    ("D5", "search"): {"query": "guidelines"},
    ("D6", "search"): {"query": "event tickets"},

    ("D1", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update", "cc": ["team@example.com"]},
    ("D2", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update"},
    ("D3", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update", "send_at": 1700000000000},
    ("D4", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update", "sender": {"email": "desk@event.org", "name": "Event Desk"}},
    ("D5", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update"},
    ("D6", "email"): {"to": "attendee@example.com", "subject": "Notice", "body": "Event update"},
}


# -----------------------------------------------------------------------------
# Sidebar: System Status & Active Drifts Monitor
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("Drift Monitor")
    st.caption("Real-time engine status and active injected drifts")

    active_drifts = injector.active_drifts()
    if active_drifts:
        st.warning(f"{len(active_drifts)} Active Drift(s) Injected")
        for drift in active_drifts:
            with st.expander(f"{drift['drift_id']} on {drift['tool'].upper()}", expanded=True):
                st.markdown(f"**Name:** {drift['drift_name']}")
                st.markdown(f"**Endpoints:** `{', '.join(drift['endpoints'])}`")
                st.markdown(f"**Fields:** `{', '.join(drift['fields'])}`")
                st.markdown(f"**Schema Visible:** {'Yes' if drift['schema_visible'] else 'No (Silent)'}")
                st.caption(drift["description"])
    else:
        st.success("Nominal State (No active drifts)")

    st.divider()

    st.subheader("Global Reset Controls")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("Reset Drifts", use_container_width=True, help="Reverts all schemas and unwraps handlers back to nominal"):
            injector.reset(ground_truth=False)
            st.toast("Active drifts reset to normal.")
            st.rerun()
    with col_r2:
        if st.button("Reset Ground Truth", use_container_width=True, help="Resets ground truth fixtures across all tools"):
            for t_info in TOOLS.values():
                t_info["module"]._reset_ground_truth()
            injector.reset(ground_truth=True)
            st.toast("Ground truth state reset across all tools.")
            st.rerun()

    st.divider()
    st.caption("API Schema Drift Project · Verification UI")


# -----------------------------------------------------------------------------
# Main Application Tabs
# -----------------------------------------------------------------------------
st.title("API Schema Drift — Exploration Dashboard")
st.markdown(
    "Interactive verification tool to inspect mock APIs, test schema drift injections, "
    "and execute multi-step workflows."
)

tab1, tab2, tab3 = st.tabs([
    "Tab 1 — Mock Tools Explorer",
    "Tab 2 — Drift Engine Playground",
    "Tab 3 — Workflow Runner",
])


# =============================================================================
# TAB 1: MOCK TOOLS EXPLORER
# =============================================================================
with tab1:
    st.subheader("Mock Tools Explorer")
    st.caption("This shows what the tool actually stored, separate from what it told the caller.")

    col1, col2 = st.columns([1, 2])

    with col1:
        selected_tool_name = st.selectbox(
            "Select Mock Tool",
            options=list(TOOLS.keys()),
            format_func=lambda name: f"{name} API",
            key="tab1_tool_select",
        )
        tool_data = TOOLS[selected_tool_name]
        tool_mod = tool_data["module"]
        tool_id = tool_data["id"]

        st.caption(tool_data["description"])

        # Endpoints from live schema
        endpoints = list(tool_mod.SCHEMA.get("endpoints", {}).keys())
        selected_endpoint = st.selectbox(
            "Select Handler / Endpoint",
            options=endpoints,
            key="tab1_endpoint_select",
        )

        ep_schema = tool_mod.SCHEMA.get("endpoints", {}).get(selected_endpoint, {})
        req_spec = ep_schema.get("request", {})
        res_spec = ep_schema.get("response", {})

        with st.expander("View Live Endpoint Schema Contract", expanded=False):
            st.json(
                {
                    "endpoint": selected_endpoint,
                    "deprecated": ep_schema.get("deprecated", False),
                    "replaced_by": ep_schema.get("replaced_by", None),
                    "request_contract": {
                        k: {
                            "type": v.get("type", str).__name__ if isinstance(v.get("type"), type) else str(v.get("type")),
                            "required": v.get("required", False),
                            "description": v.get("description", ""),
                        }
                        for k, v in req_spec.items()
                    },
                    "response_contract": {
                        k: {
                            "type": v.get("type", str).__name__ if isinstance(v.get("type"), type) else str(v.get("type")),
                            "required": v.get("required", False),
                            "description": v.get("description", ""),
                        }
                        for k, v in res_spec.items()
                    },
                }
            )

    with col2:
        st.markdown(f"#### Call `{selected_endpoint}`")

        # Build default request payload from schema & defaults
        default_payload: Dict[str, Any] = {}
        for field_name, spec in req_spec.items():
            if field_name in FIELD_DEFAULTS:
                default_payload[field_name] = copy.deepcopy(FIELD_DEFAULTS[field_name])
            elif spec.get("type") == str:
                default_payload[field_name] = f"sample_{field_name}"
            elif spec.get("type") == int:
                default_payload[field_name] = 1
            elif spec.get("type") == float:
                default_payload[field_name] = 10.0
            elif spec.get("type") == dict:
                default_payload[field_name] = {}
            elif spec.get("type") == list:
                default_payload[field_name] = []

        # Editable request JSON
        request_json_str = st.text_area(
            f"Request Payload (JSON for `{selected_endpoint}`)",
            value=json.dumps(default_payload, indent=2),
            height=180,
            key=f"tab1_payload_{selected_tool_name}_{selected_endpoint}",
        )

        execute_btn = st.button("Call Handler Live", key="tab1_exec_btn", type="primary")

        if execute_btn:
            try:
                parsed_request = json.loads(request_json_str) if request_json_str.strip() else {}
                handler_func = getattr(tool_mod, selected_endpoint)
                response = handler_func(parsed_request)
                st.session_state["tab1_last_response"] = response
                st.session_state["tab1_last_tool"] = selected_tool_name
            except Exception as e:
                st.error(f"Execution failed: {str(e)}")

    st.divider()

    col_res, col_gt = st.columns(2)

    with col_res:
        st.markdown("#### Raw API Response Returned")
        last_resp = st.session_state.get("tab1_last_response", None)
        if last_resp is not None:
            if last_resp.get("status") == "success":
                st.success("Status: SUCCESS (200 OK)")
            else:
                st.error("Status: ERROR")
            st.json(last_resp)
        else:
            st.info("Execute a handler above to view the returned API response.")

    with col_gt:
        st.markdown(f"#### {selected_tool_name} Ground Truth State (`_inspect_ground_truth()`)")
        try:
            gt_state = tool_mod._inspect_ground_truth()
            st.json(gt_state)
        except Exception as e:
            st.error(f"Failed to inspect ground truth: {e}")


# =============================================================================
# TAB 2: DRIFT ENGINE PLAYGROUND
# =============================================================================
with tab2:
    st.subheader("Drift Engine Playground")
    st.caption("Test schema and semantic drift injection across tools, comparing clean vs drifted behavior side-by-side.")

    col_t2_1, col_t2_2, col_t2_3 = st.columns([1, 1, 1])

    with col_t2_1:
        playground_tool = st.selectbox(
            "1. Select Target Tool",
            options=list(TOOLS.keys()),
            format_func=lambda name: f"{name} API",
            key="tab2_tool_select",
        )
        p_tool_data = TOOLS[playground_tool]
        p_tool_mod = p_tool_data["module"]
        p_tool_id = p_tool_data["id"]

    with col_t2_2:
        playground_drift_id = st.selectbox(
            "2. Select Drift Type (D1–D6)",
            options=list(DRIFT_DESCRIPTIONS.keys()),
            format_func=lambda d: DRIFT_DESCRIPTIONS[d],
            key="tab2_drift_select",
        )

    catalog_key = (playground_drift_id, p_tool_id)
    drift_spec = DRIFT_CATALOG.get(catalog_key, None)

    with col_t2_3:
        st.markdown("**Drift Details & Detection**")
        if drift_spec:
            st.markdown(f"**Target Endpoints:** `{', '.join(drift_spec['endpoints'])}`")
            st.markdown(f"**Affected Fields:** `{', '.join(drift_spec['fields'])}`")
            expected_detectors = ", ".join(drift_spec.get("expected_detectors", []))
            st.markdown(f"**Caught by:** `{expected_detectors}`")
            schema_vis = "Yes (Request contract changed)" if drift_spec["schema_visible"] else "No (Silent failure in response)"
            st.markdown(f"**Schema Visible:** {schema_vis}")

    if drift_spec:
        st.caption(f"**Description:** {drift_spec['description']}")

    st.divider()

    target_endpoint = drift_spec["endpoints"][0] if drift_spec and drift_spec["endpoints"] else "create_customer"

    preset_req = SAMPLE_PLAYGROUND_REQUESTS.get(
        (playground_drift_id, p_tool_id),
        {"name": "Sample User", "email": "user@example.com"}
    )

    col_req_meta, col_req_body = st.columns([1, 2])
    with col_req_meta:
        st.markdown(f"**Testing Endpoint:** `{target_endpoint}`")
        if drift_spec and len(drift_spec["endpoints"]) > 1:
            target_endpoint = st.selectbox("Target Endpoint", options=drift_spec["endpoints"], key="tab2_ep_select")

    with col_req_body:
        playground_payload_str = st.text_area(
            f"Test Request Payload (for `{target_endpoint}`)",
            value=json.dumps(preset_req, indent=2),
            height=140,
            key=f"tab2_payload_{playground_drift_id}_{p_tool_id}",
        )

    col_act1, col_act2, col_act3, col_act4 = st.columns(4)
    with col_act1:
        run_before_btn = st.button("1. Run 'Before' (Clean)", key="tab2_run_before", use_container_width=True)
    with col_act2:
        inject_btn = st.button("2. Inject Drift", type="primary", key="tab2_inject_btn", use_container_width=True)
    with col_act3:
        run_after_btn = st.button("3. Run 'After' (Drifted)", key="tab2_run_after", use_container_width=True)
    with col_act4:
        reset_playground_btn = st.button("Reset Tool", key="tab2_reset_btn", use_container_width=True)

    if "playground_before_res" not in st.session_state:
        st.session_state["playground_before_res"] = None
    if "playground_after_res" not in st.session_state:
        st.session_state["playground_after_res"] = None

    if run_before_btn:
        try:
            req_data = json.loads(playground_payload_str) if playground_payload_str.strip() else {}
            handler_func = getattr(p_tool_mod, target_endpoint)
            res = handler_func(req_data)
            st.session_state["playground_before_res"] = res
            st.toast(f"Clean call to {target_endpoint} executed successfully.")
        except Exception as e:
            st.error(f"Before call error: {e}")

    if inject_btn:
        try:
            inj_record = injector.inject(playground_drift_id, p_tool_id, allow_mid_task=True)
            st.session_state["last_injected"] = inj_record
            st.toast(f"Injected {playground_drift_id} on {playground_tool}.")
            req_data = json.loads(playground_payload_str) if playground_payload_str.strip() else {}
            handler_func = getattr(p_tool_mod, target_endpoint)
            res_after = handler_func(req_data)
            st.session_state["playground_after_res"] = res_after
            st.rerun()
        except Exception as e:
            st.error(f"Injection failed: {e}")

    if run_after_btn:
        try:
            req_data = json.loads(playground_payload_str) if playground_payload_str.strip() else {}
            handler_func = getattr(p_tool_mod, target_endpoint)
            res_after = handler_func(req_data)
            st.session_state["playground_after_res"] = res_after
            st.toast(f"Drifted call to {target_endpoint} executed.")
        except Exception as e:
            st.error(f"After call error: {e}")

    if reset_playground_btn:
        injector.reset(ground_truth=False)
        st.session_state["playground_after_res"] = None
        st.toast(f"Reset {playground_tool} to normal.")
        st.rerun()

    st.markdown("### Side-by-Side Comparison")
    col_before, col_after = st.columns(2)

    with col_before:
        st.markdown("#### BEFORE (Clean Baseline)")
        before_res = st.session_state.get("playground_before_res")
        if before_res is not None:
            st.success("Nominal Response (Pre-Drift)")
            st.json(before_res)
        else:
            st.info("Click '1. Run Before (Clean)' to capture the baseline response.")

    with col_after:
        st.markdown("#### AFTER (Drift Injected)")
        after_res = st.session_state.get("playground_after_res")
        is_active = any(d["tool"] == p_tool_id and d["drift_id"] == playground_drift_id for d in injector.active_drifts())

        if after_res is not None:
            if is_active:
                st.warning("Injected Response (Post-Drift)")
            else:
                st.info("Response (Tool Currently Reset / Normal)")
            st.json(after_res)
        else:
            st.info("Click '2. Inject Drift' or '3. Run After' to view the drifted response.")


# =============================================================================
# TAB 3: WORKFLOW RUNNER
# =============================================================================
with tab3:
    st.subheader("Workflow Runner")
    st.caption("Execute multi-step workflows across chained mock APIs and inspect intermediate step payloads and ground truth updates.")

    workflow_keys = list(WORKFLOW_REGISTRY.keys())

    def format_wf_option(w_id: str) -> str:
        w = WORKFLOW_REGISTRY[w_id]
        stakes_badge = "High Stakes" if w["stakes"] == "high" else "Low Stakes"
        tools_str = " -> ".join([t.upper() for t in w["tools"]])
        return f"{w['id']}: {w['name']} [{tools_str}] ({stakes_badge})"

    selected_wf_id = st.selectbox(
        "Select Workflow to Run",
        options=workflow_keys,
        format_func=format_wf_option,
        key="tab3_wf_select",
    )

    wf_info = WORKFLOW_REGISTRY[selected_wf_id]

    col_wf1, col_wf2, col_wf3, col_wf4 = st.columns([1, 2, 1, 1])
    with col_wf1:
        st.markdown(f"**Workflow ID:** `{wf_info['id']}`")
        stakes_color = "red" if wf_info["stakes"] == "high" else "green"
        st.markdown(f"**Stakes Level:** :{stakes_color}[{wf_info['stakes'].upper()}]")
    with col_wf2:
        st.markdown(f"**Tools Involved:** `{' -> '.join([t.upper() for t in wf_info['tools']])}`")
        st.markdown(f"**Source File:** `{wf_info['file']}`")
    with col_wf3:
        st.markdown(f"**Drift Exposure:** `{', '.join(wf_info['drift_exposure'])}`")
    with col_wf4:
        run_wf_btn = st.button("Run Workflow", type="primary", key="tab3_run_btn", use_container_width=True)

    st.divider()

    if run_wf_btn:
        try:
            runner_func = wf_info["runner"]
            result = runner_func()
            st.session_state["last_wf_result"] = result
            st.session_state["last_wf_id"] = selected_wf_id
            st.toast(f"Workflow {selected_wf_id} completed: {result.get('status')}")
        except Exception as e:
            st.error(f"Workflow execution failed: {e}")

    wf_result = st.session_state.get("last_wf_result")
    current_displayed_wf = st.session_state.get("last_wf_id")

    if wf_result and current_displayed_wf == selected_wf_id:
        if wf_result.get("status") == "success":
            st.success(f"Workflow Execution Succeeded: {wf_result.get('workflow_name')}")
        else:
            st.error(f"Workflow Execution Error: {wf_result.get('errors')}")

        st.markdown("### Step-by-Step Execution Trace")
        steps = wf_result.get("steps", [])

        for s in steps:
            s_idx = s.get("step_index", 1)
            tool_name = s.get("tool", "").upper()
            endpoint = s.get("endpoint", "")
            req = s.get("request", {})
            res = s.get("response", {})
            res_status = res.get("status", "unknown")

            with st.expander(f"Step {s_idx}: {tool_name} -> `{endpoint}` ({res_status.upper()})", expanded=True):
                col_s_req, col_s_res = st.columns(2)
                with col_s_req:
                    st.markdown("**Request Sent:**")
                    st.json(req)
                with col_s_res:
                    st.markdown("**Response Received:**")
                    if res_status == "success":
                        st.json(res)
                    else:
                        st.error(f"Step Failed: {res.get('errors', 'Unknown error')}")
                        st.json(res)

        st.markdown("### Workflow Outputs & Ground Truth State")
        col_out, col_gt_all = st.columns([1, 2])

        with col_out:
            st.markdown("**Final Workflow Outputs:**")
            st.json(wf_result.get("outputs", {}))

        with col_gt_all:
            st.markdown("**Participating Tools Ground Truth Records:**")
            for t_id in wf_info["tools"]:
                t_module = None
                for t_name, t_meta in TOOLS.items():
                    if t_meta["id"] == t_id:
                        t_module = t_meta["module"]
                        break
                if t_module:
                    with st.expander(f"{t_id.upper()} Ground Truth State", expanded=True):
                        st.json(t_module._inspect_ground_truth())

    else:
        st.info("Click **Run Workflow** above to execute this multi-step workflow live.")
