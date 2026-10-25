# CODEBASE_REPORT: API Schema Drift Resilience Evaluation

**Author:** Antigravity (Onboarding Exploration)  
**Date:** 2026-10-22  
**Target Repository:** `c:\Users\nitya\Documents\Nitya\Self\Extra - Skills\Projects\12. Major Project\API-Schema-Drift`  
**Ground Truth Context:** [docs/Context.md](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/docs/Context.md)

---

## A. Repo Map

### Directory Tree & Purpose
```
.
├── .gitignore                      # Standard Python gitignore (bytecode, venvs, cache, .env)
├── README.md                       # Project title header
├── docs/
│   └── Context.md                  # Authoritative project specification, taxonomy, architecture, & roadmap
├── drift_engine/
│   ├── __init__.py                 # Exports DriftInjector, exceptions, and handler invocation guidelines
│   └── drift_injector.py           # 30-cell drift catalog, dynamic schema patching, wrapper generator, lifecycle
├── mock_tools/
│   ├── __init__.py                 # Unified package exports for all 5 mock tools, schemas, and test utilities
│   ├── crm_api.py                  # Mock CRM tool (Salesforce/HubSpot: create, update, get, list customers)
│   ├── email_api.py                # Mock Email tool (SendGrid/Mailgun: send, get, list emails)
│   ├── payment_api.py              # Mock Payment tool (Stripe: charge, refund, get, list transactions)
│   ├── search_api.py               # Mock Search tool (Elasticsearch/Algolia: search, get_doc, get_related)
│   └── weather_api.py              # Mock Weather tool (OpenWeatherMap: current_weather, forecast, alerts)
├── test_all_tools_integration.py   # Unified 5-tool chain integration test with error path & ground truth validation
└── test_drift_injector.py          # Comprehensive 6-test suite verifying all 30 catalog cells, guards, & regression
```

### Environment, Dependencies, and Execution
- **Language & Runtime:** Python 3.13.2 (verified via `python --version` returning `Python 3.13.2`).
- **Dependencies:**
  - *Current Active Codebase:* Uses **100% Python Standard Library** (`copy`, `datetime`, `re`, `sys`, `typing`). No external packages are currently imported in any `.py` file.
  - *Target Stack (Read from [docs/Context.md:L143-155](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/docs/Context.md#L143-L155)):* Pydantic (Strategy B validation), Pandas + SQLite/CSV (logging/metrics), Streamlit (dashboard), Anthropic/OpenAI APIs (agent & Strategy C LLM check).
  - *Package Manifest:* `requirements.txt` or `pyproject.toml` is currently **MISSING / NOT FOUND**. (The user's Python environment already has `pydantic 2.12.5`, `pandas 3.0.1`, `openai 2.43.0`, `groq 0.37.1`, `langchain 1.2.13` pre-installed, verified via `pip list`).
- **Execution Commands (Verified):**
  - Run all-tools integration test: `python test_all_tools_integration.py` (Exit code: 0, verified).
  - Run drift injector test suite: `python test_drift_injector.py` (Exit code: 0, verified).
  - Run individual tool smoke test: `python -m mock_tools.crm_api` (verified for all 5 tools).

---

## B. Component Status

| Component | Status | Location | Primary Classes / Functions | Contract Summary |
|---|---|---|---|---|
| **1. Mock Tool Ecosystem** | **IMPLEMENTED** | `mock_tools/` | `crm_api.py`, `payment_api.py`, `weather_api.py`, `search_api.py`, `email_api.py` | Input: `request: dict = None, **kwargs`<br>Output: `{"status": "success", ...}` or `{"status": "error", "errors": [...]}` |
| **2. Drift-Injection Engine** | **IMPLEMENTED** | `drift_engine/` | `DriftInjector`, `DRIFT_CATALOG`, `_TOOL_MODULES` in `drift_injector.py` | Input: `inject(drift_id, tool, allow_mid_task=False)`<br>Output: Injection log record dict; patches `module.SCHEMA` and wraps module handlers |
| **3. Agent Loop** | **MISSING** | NOT FOUND | Planned: task decomposition, schema reader, request builder, LLM invoker | Specified in `docs/Context.md:L23-37`; no code files exist |
| **4. Mitigation Layer** | **MISSING** | NOT FOUND | Planned: Baseline, Strategy A (Diff Caching), Strategy B (Sanity Gating), Strategy C (LLM Self-Check) | Specified in `docs/Context.md:L42-74`; no common interface or strategy classes exist |
| **5. Task Suite** | **MISSING** | NOT FOUND | Planned: 10–15 multi-step workflows chaining 2–4 tools | One test workflow exists in `test_all_tools_integration.py:L37-252`, but no task suite code exists |
| **6. Evaluation Harness** | **MISSING** | NOT FOUND | Planned: Metric calculators (Success, Silent Failure, Misuse, Cost, Latency) | Specified in `docs/Context.md:L113-130`; no evaluation or logging harness code exists |
| **7. Experiment Runner** | **MISSING** | NOT FOUND | Planned: Task × Drift × Strategy grid executor, repetitions, seeds | Specified in `docs/Context.md:L131-141`; no runner code exists |
| **8. Dashboard / Reporting**| **MISSING** | NOT FOUND | Planned: Streamlit live drift & metric viewer | Specified in `docs/Context.md:L152`; no UI code exists |

---

### Detailed Component Breakdowns

#### 1. Mock Tool Ecosystem (`mock_tools/`)
- **Existing Tools (5):**
  1. **CRM API** ([mock_tools/crm_api.py:L11-152](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/crm_api.py#L11-L152)): Endpoints `create_customer`, `update_customer`, `get_customer`, `list_customers`.
  2. **Payment API** ([mock_tools/payment_api.py:L15-121](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/payment_api.py#L15-L121)): Endpoints `charge_customer`, `refund_customer`, `get_transaction`, `list_transactions`. Amount represents major currency units as float (e.g. `49.99` USD).
  3. **Weather API** ([mock_tools/weather_api.py:L15-74](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/weather_api.py#L15-L74)): Endpoints `get_current_weather`, `get_forecast`, `get_alerts`. Metric units: °C (float), m/s (float), % (int).
  4. **Search API** ([mock_tools/search_api.py:L11-77](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/search_api.py#L11-L77)): Endpoints `search`, `get_document`, `get_related_documents`. 12-document corpus fixture with keyword-overlap scoring ([mock_tools/search_api.py:L80-186](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/search_api.py#L80-L186)).
  5. **Email API** ([mock_tools/email_api.py:L11-90](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/email_api.py#L11-L90)): Endpoints `send_email`, `get_email`, `list_emails`. Outbox queue state.
- **Schema Storage & Versioning:** Schemas are stored as module-level dictionaries (`SCHEMA`) inside each tool module. Handlers and validation routines read `SCHEMA` dynamically at call-time (enabling in-memory patching without disk I/O). No static version files (e.g. `v1.json`) exist.
- **Ground Truth Isolation:** Each tool defines a private `_GROUND_TRUTH` dictionary (`customers`, `transactions`/`refunds`, `_WEATHER_DATA`/`request_log`, `corpus`/`request_log`, `outbox`). Handlers call `_extract_recognized_fields()` to store *only schema-recognized fields* into ground truth, allowing silent failures to be detected when an unrecognised or renamed field is silently omitted from persistence ([mock_tools/crm_api.py:L223-260](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/mock_tools/crm_api.py#L223-L260)).
- **Inspection & Teardown Contract:** Every module exposes `_inspect_ground_truth() -> dict` (returns deep copy) and `_reset_ground_truth() -> None`.

#### 2. Drift-Injection Engine (`drift_engine/`)
- **Supported Drift Types (D1–D6):**
  - **D1: Request Field Rename** (`schema_visible=True`) — e.g. CRM `phone` -> `Phone_Number`, Search `max_results` -> `limit`.
  - **D2: Response Format/Type Change** (`schema_visible=False`) — e.g. CRM epoch -> ISO-8601 string, Payment float -> `"50.00"` string, Weather humidity int -> `"62%"` string.
  - **D3: Value Meaning/Unit Change** (`schema_visible=False`) — e.g. Payment dollars -> cents (x100), Weather wind m/s -> km/h (x3.6), Email `send_at` s -> ms.
  - **D4: Nested ↔ Flat Structure** (`schema_visible=True`) — e.g. CRM `address` dict flattened to `address_street`, etc.; Payment `payment_method` str nested to dict; Weather `city`/`country_code` nested to `location` dict.
  - **D5: Silent Null Value** (`schema_visible=False`) — e.g. CRM customer `email: None`, Payment `transaction_id: None`, Weather `temperature: None`.
  - **D6: Endpoint Deprecation with Fallback** (`schema_visible=True`) — marks endpoint deprecated in schema, exposes `<endpoint>_v2`, returns static dummy payload without touching ground truth.
- **30-Cell Catalog:** Complete 6 × 5 matrix implemented in `DRIFT_CATALOG` ([drift_engine/drift_injector.py:L58-455](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/drift_injector.py#L58-L455)).
- **Configuration & Triggers:**
  - Class `DriftInjector` accepts `schedule: Optional[Dict[int, List[Tuple[str, str]]]]` triggered at task boundaries via `on_task_boundary(task_index)` ([drift_engine/drift_injector.py:L850-858](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/drift_injector.py#L850-L858)).
  - Mid-task guard enforces that `inject()` cannot be called while `_in_task == True` unless `allow_mid_task=True`, raising `MidTaskInjectionError` ([drift_engine/drift_injector.py:L877-881](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/drift_injector.py#L877-L881)).
  - Stacking & Conflict Checking: Multiple non-conflicting drifts can stack across tools. Conflicts on the same tool/endpoint/field raise `ConflictingDriftError` ([drift_engine/drift_injector.py:L888-897](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/drift_injector.py#L888-L897)).
- **Determinism:** Fully deterministic transformations, verified by assertion in `test_drift_injector.py:L288-307`. Does not rely on random number generators.

#### 3. Agent Loop
- **Status:** MISSING / NOT FOUND.
- **Details:** No files exist for task decomposition, step execution, prompt construction, LLM provider integration, or tool calling.

#### 4. Mitigation Layer (Baseline, Strategy A, Strategy B, Strategy C)
- **Status:** MISSING / NOT FOUND.
- **Details:** No swappable strategy base classes, decorators, or middleware exist. Strategy A (Diff Caching), Strategy B (Pydantic rule gating), and Strategy C (LLM semantic check) must be constructed from scratch adhering to [docs/Context.md:L42-86](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/docs/Context.md#L42-L86).

#### 5. Task Suite
- **Status:** MISSING / NOT FOUND.
- **Details:** The planned 10–15 multi-step workflows chaining 2–4 tools are not yet implemented as runnable code or test assets (noted in [docs/Context.md:L190](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/docs/Context.md#L190)). Only a single hardcoded sequence exists in `test_all_tools_integration.py`.

#### 6. Evaluation Harness
- **Status:** MISSING / NOT FOUND.
- **Details:** Formulas for Task Success Rate, Silent Failure Rate, Interface Misuse Rate, Cost Overhead, and Latency are defined in [docs/Context.md:L117-124](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/docs/Context.md#L117-L124), but no code exists to compute, record, or persist them.

#### 7. Experiment Runner
- **Status:** MISSING / NOT FOUND.
- **Details:** No runner script exists to iterate across Tasks × Drift Types × Strategies.

#### 8. Dashboard / Demo
- **Status:** MISSING / NOT FOUND.
- **Details:** No Streamlit or Gradio applications exist in the repo.

---

## C. Data Flow

### Current Executable Data Flow (Test Execution)
```
test_all_tools_integration.py / test_drift_injector.py
  │
  ├── 1. DriftInjector.inject(drift_id, tool)
  │      ├── Patches target module.SCHEMA
  │      └── Wraps target module handler: setattr(module, ep, wrapped_handler)
  │
  ├── 2. Caller executes: module.<endpoint>(request_dict)
  │      │
  │      ├── wrapped_handler intercepts call:
  │      │     ├── Validates request against live drifted module.SCHEMA via module._validate()
  │      │     ├── Intercepts D6 fallback if deprecated
  │      │     ├── Silently drops keys absent from drifted request schema
  │      │     ├── Applies request_transform() (adapts to original contract)
  │      │     ├── Temporarily sets module.SCHEMA = original_schema
  │      │     ├── Calls orig_handler(transformed_req)
  │      │     │      ├── Extracts schema-recognized fields
  │      │     │      ├── Updates module._GROUND_TRUTH
  │      │     │      └── Returns raw response dict
  │      │     ├── Restores module.SCHEMA = drifted_schema
  │      │     └── Applies response_transform() (e.g., ISO timestamp, minor units, etc.)
  │      │
  │      └── Returns drifted response dict to caller
  │
  └── 3. Test verification checks:
         ├── Inspects returned response dict
         ├── Calls module._inspect_ground_truth()
         └── Asserts ground truth matches or reveals silent failure
```

### Planned Research Pipeline Data Flow
```
Task Suite (Natural Language Prompt + Expected Ground Truth)
  │
  ▼
AI Agent Loop (Decomposes task into tool steps)
  │
  ├── Reads live Tool SCHEMA (call-time contract)
  ├── Builds Request Payload
  │
  ▼
Mitigation Layer (Pre-Call)
  ├── Baseline: Direct pass-through
  └── Strategy A: Compares live schema hash against cached hash
        └── If mismatch: reloads schema, triggers agent prompt adaptation
  │
  ▼
Mock Tool Execution (Module Handler via wrapped attribute)
  ├── Validates against drifted SCHEMA
  ├── Mutates private _GROUND_TRUTH
  └── Produces Raw / Drifted Response
  │
  ▼
Mitigation Layer (Post-Call)
  ├── Baseline: Direct pass-through to Agent
  ├── Strategy B: Pydantic response rule validation (types, formats, plausible ranges)
  │     └── If invalid: rule-based correction or rejection
  └── Strategy C: LLM Self-Check (reasons if response makes semantic sense for task)
        └── If suspicious: doc verification, unit conversion, or halt & notify
  │
  ▼
Agent Loop (Processes response, executes next step until task termination)
  │
  ▼
Evaluation Harness
  ├── Inspects mock tool _inspect_ground_truth() vs. Task Expected State
  ├── Computes Metrics:
  │     ├── Task Success Rate (did final state match expected?)
  │     ├── Silent Failure Rate (reported success, but ground truth missing/corrupt?)
  │     ├── Interface Misuse Rate (malformed requests sent)
  │     ├── Cost Overhead (mitigation API/LLM tokens/calls)
  │     └── Latency Overhead (wall-clock time added)
  └── Logs Run Record to SQLite/CSV/Pandas
```

---

## D. Conventions & Standards

- **Code Style:** Clean, idiomatic Python with type annotations on function arguments and return types. PEP 8 standard formatting with 4-space indentation.
- **Config & Schema Format:** In-code Python data structures (`dict`). No JSON/YAML config loading. All schema definitions reside directly in `SCHEMA` dictionaries within each tool file.
- **Invocation Convention (CRITICAL):** Tools **must always** be invoked as module attributes (e.g. `crm_api.create_customer(...)` or `module.create_customer(...)`). Importing directly via `from mock_tools.crm_api import create_customer` bypasses `DriftInjector`'s dynamically patched module attributes ([drift_engine/__init__.py:L6-9](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/__init__.py#L6-L9)).
- **Identifiers & Formatting Standards:**
  - IDs use typed prefixes with 4-digit zero-padding: `cust_0001`, `tx_0001`, `ref_0001`, `msg_0001`, `doc_001`.
  - Timestamps: Unix epoch integer seconds (base `1700000000`).
  - Money & Weather numbers: standard `float` for currency amounts and temperatures.
- **State & Test Hygiene:** Every mock tool implements `_inspect_ground_truth()` and `_reset_ground_truth()`. Tests always reset ground truth before and after execution.
- **Error Handling:** Handlers return structured error dicts `{"status": "error", "errors": [...]}` instead of throwing exceptions. Engine misuse raises explicit custom exceptions (`MidTaskInjectionError`, `ConflictingDriftError`, `InvalidDriftError`, `UnknownToolError`).
- **Test Results (Verified Running Locally):**
  - `python test_all_tools_integration.py` -> **PASSED** (8/8 steps, ground truth asserted across all 5 tools, validation error paths asserted).
  - `python test_drift_injector.py` -> **PASSED** (30/30 catalog cells verified, silent failure demonstrated, drift stacking verified, mid-task guard verified, determinism verified, post-reset regression verified).

---

## E. Gaps, Risks, and Observations

1. **Unimplemented Roadmap Components (Phases 2–6):**
   - The entire upper half of the system (Agent loop, Mitigation Layer Strategies A/B/C, Task suite, Evaluation harness, Experiment runner, and Dashboard) is currently absent.
2. **Missing Package Manifest:**
   - No `requirements.txt` or `pyproject.toml` exists in the repo root to specify pinned versions of future dependencies (`pydantic`, `streamlit`, `pandas`, `openai`, `anthropic`).
3. **Execution Parallelism & Thread Safety:**
   - Both mock tools and `DriftInjector` mutate shared module-level state (`module.SCHEMA`, `module._GROUND_TRUTH`, `setattr(module, ep, ...)`).
   - If experiment runs are executed across multiple threads in the same process, cross-talk and race conditions will occur. Experiments must either run sequentially or use process-based multiprocessing (`multiprocessing` / sub-processes).
4. **Tool Import Pattern Risk:**
   - In `mock_tools/__init__.py`, handlers are imported directly (`from mock_tools.crm_api import create_customer`). If an agent imports from `mock_tools` directly (`from mock_tools import create_customer`), it binds to the original function object before `DriftInjector` patches `crm_api.create_customer`. The agent loop must import modules (e.g. `import mock_tools.crm_api as crm_api`) or use a dispatcher mapping.
5. **D3 (Value Meaning Change) Handling in CRM:**
   - In `drift_injector.py:L87`, D3 targets `annual_revenue`, but `crm_api.py` does not have a top-level `annual_revenue` field in its baseline `SCHEMA`. The transform handles this by looking into `metadata` or top-level if provided. Tasks utilizing CRM D3 must be aware of this contract.
6. **Floating Point Rounding:**
   - Handlers use standard Python `float` and `round(..., 4)` for currencies and scores. While sufficient for mock purposes, comparisons in evaluation assertions should account for float precision or format strings.
7. **Simplification Opportunities:**
   - The wrapper logic in `DriftInjector._create_wrapper` ([drift_engine/drift_injector.py:L957-1004](file:///c:/Users/nitya/Documents/Nitya/Self/Extra%20-%20Skills/Projects/12.%20Major%20Project/API-Schema-Drift/drift_engine/drift_injector.py#L957-L1004)) handles multiple overlapping drifts cleanly; maintaining this zero-mock-edit dynamic wrapping strategy keeps mock tools completely free of test-injection boilerplate.

---

## F. Readiness Summary

### Current State Summary (10 Lines)
1. Phase 1 mock tool ecosystem is fully implemented, self-contained, and verified across all 5 mock APIs (CRM, Payment, Weather, Search, Email).
2. Phase 1 drift engine is fully implemented with a complete 30-cell catalog covering 6 distinct drift taxonomies (D1–D6) across all 5 tools.
3. Ground truth state is cleanly isolated from API response payloads in all mock tools, enabling rigorous Silent Failure Rate measurement.
4. Drift injection is non-destructive, dynamic, and reversible via module-level schema patching and handler wrapping without editing tool source files.
5. Deterministic execution and mid-task boundary protection are implemented and verified via comprehensive test suites.
6. Both existing test suites (`test_all_tools_integration.py` and `test_drift_injector.py`) run locally and pass 100%.
7. The codebase currently has zero external dependencies, operating entirely on Python standard library 3.13.2.
8. No task workflow suite (10–15 multi-step tasks) has been coded yet; only one test scenario exists in the integration test.
9. No Agent loop, LLM provider integration, or Mitigation Layer (Baseline, Strategy A, Strategy B, Strategy C) has been implemented yet.
10. No Evaluation harness, experiment matrix runner, or Streamlit dashboard has been built yet.

### Key Files for Typical Next Steps
| Next Step Goal | Primary Files to Touch / Create |
|---|---|
| **Build Agent Loop** | Create `agent/agent_loop.py`, `agent/prompts.py`, `agent/llm_client.py` |
| **Implement Mitigation Layer** | Create `mitigation/base.py`, `mitigation/strategy_a.py`, `mitigation/strategy_b.py`, `mitigation/strategy_c.py` |
| **Implement Task Suite** | Create `tasks/task_definitions.py`, `tasks/task_runner.py` (implementing 10–15 workflows) |
| **Add / Tune Drift Types** | Modify `drift_engine/drift_injector.py` (`DRIFT_CATALOG` and transform helpers), update `test_drift_injector.py` |
| **Build Evaluation & Logging Harness** | Create `evaluation/metrics.py`, `evaluation/logger.py` |
| **Run Experiment Grid** | Create `experiments/run_experiments.py` |
| **Build Dashboard** | Create `dashboard/app.py` (Streamlit) |

### Open Questions Before Next Task
1. **Target Task for Next Step:** Should we proceed with **Task 1.4 (Coding the 10–15 Task Workflow Suite)**, or jump directly to **Phase 2 (Agent Loop and Strategy A implementation)**?
2. **LLM Provider & Model Selection:** Which LLM provider and model will be the primary target for the Agent loop and Strategy C (e.g. OpenAI `gpt-4o`/`gpt-4o-mini`, Anthropic `claude-3-5-sonnet`, or Groq / open-source via LangChain/LiteLLM)?
3. **Agent Architecture Style:** Do you prefer a lightweight custom function-calling loop (plain Python calling the LLM API directly) or an orchestration framework (e.g. LangChain / LangGraph)?
4. **Task Suite Structure:** For the 10–15 tasks, should they be stored as structured declarative data (e.g. JSON/YAML/Pydantic schemas with steps, parameters, and expected ground truth checks) or Python generator functions?
