# Project Context: Schema Drift Resilience for Tool-Using AI Agents

> **Instructions for the AI agent reading this file:** This is the full, authoritative context for this project. Treat it as ground truth for scope, terminology, and architecture. If a request seems to contradict this document, flag the conflict instead of silently deviating from it. Do not introduce new mitigation strategies, metrics, or drift types beyond what's defined here without explicit confirmation from the user.

---

## 1. Problem Statement

AI agents perform real-world tasks by calling external APIs (CRM, payment, email, search, etc.) — they don't act directly, they depend entirely on these tools.

**The core problem:** APIs evolve continuously — providers rename fields, change data types, flip required/optional status, restructure responses, or deprecate endpoints, often without warning. This is **API Schema Drift**.

**The dangerous case — Silent Failure:** The API still returns a response that *looks* successful, but the underlying meaning of the data has silently changed. The agent believes the task succeeded while the real result is wrong.

> Example: A CRM originally accepts `Name`, `Phone`, `Email`. It's silently updated to require `Name`, `Phone_Number`, `Email`, `Country_Code`. The agent still sends `Phone = 9876543210`. The API still returns `Status: Success`. The phone number was never actually stored.

**Research objective:** Build a system that automatically detects schema drift and recovers from it *before* incorrect actions are taken, and determine which mitigation strategy best detects/recovers from drift while keeping cost and latency low.

---

## 2. System Architecture

```
User → AI Agent → Reads Tool Schema → Builds API Request →
Mitigation Layer → Mock API → Mitigation Layer (validates response) →
AI Agent → Next Task → Evaluation System
```

1. User gives a natural-language task (e.g., "Create a customer named Rahul and send him a welcome email").
2. Agent decomposes the task into steps (plan only).
3. Agent reads the tool's schema before calling any API.
4. Agent builds the request using that schema.
5. Request passes through a **Mitigation Layer** (one of three strategies, or none — baseline).
6. Mock API executes the request, returns a response.
7. Response passes back through the Mitigation Layer before the agent trusts it.
8. Agent proceeds to the next step; process repeats.

All three strategies (and a no-mitigation baseline) are tested against **identical** injected drift conditions for fair comparison.

---

## 3. The Three Mitigation Strategies

### Strategy A — Schema-Diff Caching
- **Method:** Hash the schema on first read; before every future call, re-hash the live schema and compare to the cached hash.
- **Detects:** Structural drift (rename, add/remove field, required↔optional flip).
- **Recovery:** Hash mismatch → reload full schema → identify what changed → rebuild request → update cache.
- **Blind spot:** Non-obvious renames (`Phone` → `Contact`) need a reasoning assist (heuristic/LLM) since hashing alone can't map old→new. **Cannot detect semantic drift at all** (e.g., `price` silently switching dollars→cents) — the hash stays identical.
- **Cost:** Very fast, very cheap — local hashing only, no LLM calls.

### Strategy B — Sanity-Check Gating
- **Method:** Validates API responses against rules — required fields present, correct types, values in plausible range (implemented via Pydantic).
- **Detects:** Format/validity drift (wrong type, missing field, out-of-range value).
- **Recovery:** Failed validation → attempt a confident rule-based correction (e.g., "Twenty-One" → 21) → re-validate. If correction isn't possible with high confidence, reject and retry/reload schema — never guess silently.
- **Blind spot:** Only checks format/range, not meaning. `Fee = 400` passes every rule even if it should mean $4.00, not 400 cents/dollars misread.
- **Edge cases:** Ambiguous text ("25ish") → reject, don't guess. Non-numeric ("N/A") → treat as missing, not a format issue. Locale-specific number formats → known limitation.
- **Cost:** Fast and cheap — rule evaluation only, no LLM calls.

### Strategy C — LLM Self-Check (main contribution)
- **Method:** A second LLM reasons: "does this response actually make sense given the task context?"
- **Detects:** Semantic drift — structurally/formally valid data that doesn't logically fit.
- **Recovery:** If flagged suspicious → reload API docs to check for undocumented changes → if a plausible explanation is found, convert/correct the value → re-check plausibility → proceed if resolved. If ambiguity can't be resolved confidently, **halt and notify the user** — especially for high-stakes actions like payments.
- **Blind spot:** Highest cost/latency (extra LLM call per check); its own judgment reliability must be validated against a hand-labeled test set before being trusted.
- **Cost:** Highest cost and latency of the three, but the only layer that catches meaning-level problems A and B structurally cannot.

### Tying-Together Example (all three strategies, one scenario)
Task: *"Sign up Rahul as a premium member — create his customer record and charge his membership fee."* (CRM + Payment APIs). Three drifts occur simultaneously:
1. CRM: `Phone` → `Contact` (structural) — caught by **Strategy A** (needs reasoning assist since it's not an obvious substring match).
2. Payment: `Eligible_Age` returns `"Twenty-One"` instead of `21` (format) — caught by **Strategy B**.
3. Payment: `Fee` silently switches dollars→cents ($4 fee returns as `400`) (semantic) — only **Strategy C** catches this, by reasoning that a $400-ish membership fee is implausible, then confirming via docs that the field is now "amount in cents."

**Takeaway:** Each strategy's blind spot motivates the next layer. The practical conclusion is a **layered approach** (A + B always-on, cheap; C invoked selectively for high-risk actions) — not "one strategy wins."

---

## 4. Confidence Scoring (for Strategy C)

| Approach | Method | Limitation |
|---|---|---|
| Direct Self-Reported Confidence | LLM outputs judgment + confidence score (0–100) | Not mathematically calibrated; can be overconfident |
| Log-Probability / Token-Level Confidence | Read the model's internal probability for its answer token | Not all APIs expose this; harder to interpret |
| Consistency-Based Confidence | Run the same check 3–5 times; confidence = agreement rate | Most expensive — multiple LLM calls per single check |

**Usage:** High confidence → proceed to recovery directly. Medium → investigate further before acting. Low/ambiguous → don't act silently; retry the check, or halt and notify the user for high-stakes actions.

---

## 5. Mock Tool Ecosystem & Drift Injection

**Why mock APIs, not real ones:** Control (can't force real providers to drift on schedule), repeatability (identical conditions across baseline + A + B + C), safety (no real PII, no breaking live production systems).

**Mock tools (5):** CRM, Payment, Weather, Search, Email — each built as a **schema + handler pair** (plain Python, no networking).

Each mock tool has:
- **SCHEMA** — the current contract (fields, types, required/optional)
- **Ground truth state** — private internal "real" data, separate from what's returned to the agent (essential for measuring Silent Failure Rate)
- **Handlers** — the functions the agent actually calls; validate against SCHEMA, mutate ground truth, return a response

**Five drift types the injection engine supports:**
1. Field rename (`Phone` → `Phone_Number`)
2. Data type change (dollars→cents, string→number)
3. Required ↔ Optional field flip
4. Nested ↔ Flat structure change
5. Endpoint deprecation

Drift is injected **between tasks at a controlled point**, not mid-task.

**Task/workflow suite:** 10–15 realistic multi-step workflows, each requiring 2–4 chained mock APIs (e.g., CRM → Payment → Email). Should collectively give good field/tool coverage across all 5 drift types, and include a mix of high-stakes (payments) and low-stakes (lookups) tasks.

---

## 6. Evaluation Metrics

Logged for every (task × drift type × strategy) run, including a no-mitigation baseline:

| # | Metric | What it measures | Formula |
|---|---|---|---|
| 1 | Task Success Rate | Did the task complete correctly overall? | (Correct completions) ÷ (Total tasks) × 100 |
| 2 | **Silent Failure Rate** (primary) | Agent reported success, but was the data actually correct? | (Reported-success runs that were actually wrong) ÷ (Total reported-success runs) × 100 |
| 3 | Interface Misuse Rate | How often the agent sends a malformed/incorrect request | (Malformed requests) ÷ (Total requests) × 100 |
| 4 | Cost Overhead | Extra API/LLM calls added by mitigation vs. baseline | (Calls with mitigation) − (Calls in baseline) |
| 5 | Latency | Extra time added by mitigation vs. baseline | (Time with mitigation) − (Time in baseline) |

**Silent Failure Rate is the headline metric** — it's the direct, measurable form of the core problem (Task Success Rate alone can hide an agent that "succeeded" while quietly corrupting data).

**Fairness rule:** every strategy (and baseline) is tested against the exact same task, same injected drift, same point in the workflow — only the active strategy varies.

---

## 7. Experimental Procedure & Expected Results

For each run: select task → select drift type → activate condition (baseline/A/B/C) → inject drift → execute workflow → record all 5 metrics. Repeat across the full grid (tasks × drift types × conditions).

**Hypothesis (stated honestly, not claiming a single winner):**
- Strategy A: fastest/cheapest, structurally blind to semantic drift.
- Strategy B: cheap, catches format/validity issues, blind to values that are valid-but-meaningless.
- Strategy C: catches semantic drift the others miss, at higher cost/latency.
- **Likely conclusion:** a layered recommendation — run A and B by default, invoke C selectively for higher-risk actions.

---

## 8. Tech Stack

| Category | Item | Used for |
|---|---|---|
| Language | Python 3 | Core implementation |
| LLM API | Anthropic/OpenAI | Agent reasoning + Strategy C's self-check |
| Communication | Direct function calls | Agent ↔ mock-tool (no network layer needed) |
| Validation | Pydantic | Strategy B's schema validation engine |
| Hashing | Python `hashlib` / `json` (stdlib) | Strategy A's schema hashing & diffing |
| Dashboard | Streamlit | Live drift-detection & metrics dashboard |
| Logging/Analysis | Pandas + SQLite/CSV | Experiment logging and metrics analysis |
| Version control | GitHub | Final repo deliverable |

---

## 9. Project Timeline

| Phase | Dates | Tasks |
|---|---|---|
| **Phase 1** | Aug – Sept | 1.1 Literature/web review · 1.2 Build the mock-tool ecosystem · 1.3 Build the drift-injection engine · 1.4 Design the 10–15 task workflow suite |
| **Phase 2** | Oct | 2.1 Build the agent loop (task decomposition, schema reading, request building, step sequencing) · 2.2 Implement Strategy A |
| **Phase 3** | Nov – Dec | 3.1 Implement Strategy B · 3.2 Implement Strategy C · 3.3 Write research paper 1 (literature survey) |
| **Phase 4** | Jan | 4.1 Build the evaluation harness (orchestrates task × drift type × condition grid runs) · 4.2 Build logging pipeline capturing all 5 metrics per run · 4.3 Build a hand-labeled validation set for Strategy C + implement/tune a confidence-scoring approach |
| **Phase 5** | Jan – Feb | 5.1 Run the full experiment grid · 5.2 Validate and tune Strategy C's confidence thresholds against the hand-labeled set · 5.3 Analyze results |
| **Phase 6** | Feb – Mar | 6.1 Write the technical research paper 2 · 6.2 Polish the Streamlit dashboard for live drift detection and metrics viewing · 6.3 Clean up and finalize the GitHub repository |

---

## 10. Current Progress Log

> Keep this section updated as work progresses, so any agent picking up the project mid-stream knows exactly where things stand.

- [x] Task 1.2 (in progress): Mock-tool pattern established — `mock_tools/crm_api.py` and `mock_tools/payment_api.py` built and smoke-tested. Each follows the SCHEMA → ground truth → handlers pattern. Chained CRM → Payment workflow test (`test_workflow_chain.py`) passes end-to-end.
- [x] Task 1.2: Email, Weather, and Search mock tools built and smoke-tested (`mock_tools/email_api.py`, `mock_tools/weather_api.py`, `mock_tools/search_api.py`). Chained Search → Weather → Email workflow test (`test_email_weather_search_chain.py`) passes end-to-end.
- [ ] Task 1.3: Drift-injection engine — not started.
- [ ] Task 1.4: 10–15 task workflow suite — design drafted conversationally, not yet implemented as code.

---

## 11. Ground Rules for Any AI Agent Working on This Project

1. **Don't invent new strategies, metrics, or drift types.** Stick to the three strategies, five metrics, and five drift types defined above.
2. **Every mock tool must expose ground truth separately from its response** — this is non-negotiable, it's required for Silent Failure Rate.
3. **Drift is injected between tasks, not mid-task**, unless explicitly told otherwise.
4. **Don't silently "fix" or guess on ambiguous data** — that's exactly the failure mode this project studies. When unsure, flag it rather than resolving it quietly.
5. **Keep mock tools as plain Python function calls**, not real network calls — speed and control matter more than realism here.
6. If a request would change the architecture, metrics, or scope described in this document, **say so explicitly** before proceeding, rather than adapting silently.