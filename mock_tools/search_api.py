"""Mock Search API tool following Elasticsearch/Algolia conventions.

Implements query searching, document retrieval, and related document discovery over a
deterministic corpus using keyword-overlap relevance scoring.
"""

import copy
import re

# 1. SCHEMA: Module-level contract definition.
SCHEMA = {
    "tool": "search",
    "endpoints": {
        "search": {
            "request": {
                "query": {
                    "type": str,
                    "required": True,
                    "description": "Search query keywords string",
                },
                "max_results": {
                    "type": int,
                    "required": False,
                    "description": "Maximum number of search results to return per page",
                },
                "page": {
                    "type": int,
                    "required": False,
                    "description": "1-indexed page number for pagination",
                },
                "filters": {
                    "type": dict,
                    "required": False,
                    "description": "Key-value metadata filter criteria",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "results": {"type": list, "required": True, "description": "List of matching result objects ({id, title, snippet, score})"},
                "total": {"type": int, "required": True, "description": "Total count of matching documents"},
                "page": {"type": int, "required": True, "description": "1-indexed current page number"},
            },
        },
        "get_document": {
            "request": {
                "document_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the document to retrieve",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "document": {"type": dict, "required": False, "description": "Full document record"},
            },
        },
        "get_related_documents": {
            "request": {
                "document_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the target document",
                },
                "max_results": {
                    "type": int,
                    "required": False,
                    "description": "Maximum number of related documents to return",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "results": {"type": list, "required": True, "description": "List of related document result objects"},
                "total": {"type": int, "required": True, "description": "Total count of related documents"},
            },
        },
    },
}

# 2. Ground truth state: Read-only corpus fixture dataset and private request log.
_CORPUS = [
    {
        "id": "doc_001",
        "title": "Outdoor Event Safety Guidelines",
        "body": "Outdoor events can proceed if temperature is below 35 degrees C and no active severe weather alerts exist. If heavy rain or thunderstorm warnings are active, relocate indoors or reschedule.",
        "snippet": "Outdoor events can proceed if temperature is below 35 degrees C and no active severe weather alerts exist.",
        "category": "guidelines",
    },
    {
        "id": "doc_002",
        "title": "Event Cancellation and Refund Policy",
        "body": "Full refunds are issued if an event is cancelled due to adverse weather conditions at least 24 hours prior to scheduled start time.",
        "snippet": "Full refunds are issued if an event is cancelled due to adverse weather conditions...",
        "category": "policy",
    },
    {
        "id": "doc_003",
        "title": "Venue Equipment Operations",
        "body": "All outdoor audio and lighting equipment must be shut down and secured if wind speeds exceed 10 m/s or relative humidity exceeds 90%.",
        "snippet": "Equipment must be secured if wind speeds exceed 10 m/s or humidity exceeds 90%.",
        "category": "operations",
    },
    {
        "id": "doc_004",
        "title": "Attendee Notification Protocols",
        "body": "Event organizers must issue email notifications to all attendees with go or no-go status updates at least 4 hours before the event.",
        "snippet": "Issue email notifications to attendees with go or no-go status updates...",
        "category": "communication",
    },
    {
        "id": "doc_005",
        "title": "Weather Contingency Plan Template",
        "body": "A weather contingency plan requires daily temperature, humidity, and wind speed monitoring for all outdoor venues across India.",
        "snippet": "Contingency plan requires daily weather monitoring for outdoor venues...",
        "category": "guidelines",
    },
    {
        "id": "doc_006",
        "title": "Mumbai Venue Operations Guide",
        "body": "Coastal venue locations in Mumbai require special coastal weather checks. Monitor monsoon warnings closely during outdoor setup.",
        "snippet": "Coastal venue locations in Mumbai require special coastal weather checks.",
        "category": "venue",
    },
    {
        "id": "doc_007",
        "title": "Delhi Event Logistics",
        "body": "High heat protocols apply when temperatures exceed 38 degrees C in Delhi venues. Shaded seating and water stations must be provided.",
        "snippet": "High heat protocols apply when temperatures exceed 38 degrees C in Delhi venues.",
        "category": "venue",
    },
    {
        "id": "doc_008",
        "title": "Bengaluru Open Air Concert Rules",
        "body": "Open air concerts in Bengaluru require noise permission clearance and rain contingency covers for main stages.",
        "snippet": "Open air concerts require rain contingency covers for main stages.",
        "category": "venue",
    },
    {
        "id": "doc_009",
        "title": "VIP Ticketing & Access Control",
        "body": "VIP ticket holders are entitled to premium covered seating areas and priority check-in queues at all venues.",
        "snippet": "VIP ticket holders are entitled to premium covered seating areas...",
        "category": "ticketing",
    },
    {
        "id": "doc_010",
        "title": "Food & Beverage Safety Regulations",
        "body": "Food catering stalls must maintain temperature control for perishable items during outdoor events.",
        "snippet": "Food catering stalls must maintain temperature control for perishable items...",
        "category": "operations",
    },
    {
        "id": "doc_011",
        "title": "Emergency Evacuation Plan",
        "body": "In case of severe weather or structural hazards, security teams will guide attendees to designated shelter zones.",
        "snippet": "Security teams will guide attendees to designated shelter zones in emergency.",
        "category": "safety",
    },
    {
        "id": "doc_012",
        "title": "Email Template Guide for Event Updates",
        "body": "Email subjects for status updates should follow format: Event Update: [Name] - [Go/No-Go]. Include forecast temperature in body.",
        "snippet": "Include temperature forecast and clear go/no-go recommendation in email body.",
        "category": "communication",
    },
]

_GROUND_TRUTH = {
    "corpus": _CORPUS,
    "request_log": [],
}


# Helper scoring function: simple keyword-overlap score normalized [0.0, 1.0].
def _score_document(query: str, doc: dict) -> float:
    """Calculates a keyword-overlap relevance score between 0.0 and 1.0."""
    query_words = set(re.findall(r"\w+", query.lower()))
    if not query_words:
        return 0.0

    text = f"{doc['title']} {doc['body']} {doc['snippet']}".lower()
    doc_words = set(re.findall(r"\w+", text))

    overlap = len(query_words.intersection(doc_words))
    score = overlap / len(query_words)
    return min(round(score, 2), 1.0)


# 3. _validate: Schema validation engine reading SCHEMA at call time.
def _validate(endpoint: str, request: dict) -> list[str]:
    """Validates a request dictionary against the live SCHEMA definition."""
    errors = []
    if not isinstance(request, dict):
        return ["Request must be a dictionary"]

    endpoints = SCHEMA.get("endpoints", {})
    if endpoint not in endpoints:
        return [f"Unknown endpoint: '{endpoint}'"]

    req_schema = endpoints[endpoint].get("request", {})
    for field_name, field_def in req_schema.items():
        expected_type = field_def.get("type")
        is_required = field_def.get("required", False)

        if field_name not in request or request[field_name] is None:
            if is_required:
                errors.append(f"Missing required field: '{field_name}'")
            continue

        val = request[field_name]

        if expected_type is int:
            if isinstance(val, bool) or not isinstance(val, int):
                errors.append(f"Field '{field_name}' must be of type int, got {type(val).__name__}")
        elif expected_type is float:
            if isinstance(val, bool) or not isinstance(val, (float, int)):
                errors.append(f"Field '{field_name}' must be of type float, got {type(val).__name__}")
        elif expected_type is str:
            if not isinstance(val, str):
                errors.append(f"Field '{field_name}' must be of type str, got {type(val).__name__}")
        elif expected_type is list:
            if not isinstance(val, list):
                errors.append(f"Field '{field_name}' must be of type list, got {type(val).__name__}")
        elif expected_type is dict:
            if not isinstance(val, dict):
                errors.append(f"Field '{field_name}' must be of type dict, got {type(val).__name__}")

    return errors


def _extract_recognized_fields(endpoint: str, request: dict) -> dict:
    """Extracts only fields recognized by the current SCHEMA endpoint definition."""
    req_schema = SCHEMA.get("endpoints", {}).get(endpoint, {}).get("request", {})
    extracted = {}
    for field_name in req_schema:
        if field_name in request and request[field_name] is not None:
            extracted[field_name] = request[field_name]
    return extracted


def _log_request(endpoint: str, request: dict, response: dict) -> None:
    """Logs request and response to private ground truth log."""
    _GROUND_TRUTH["request_log"].append(
        {
            "endpoint": endpoint,
            "request": copy.deepcopy(request),
            "response": copy.deepcopy(response),
        }
    )


# 4. Handler functions: Validate request, read ground truth, return response.
def search(request: dict = None, **kwargs) -> dict:
    """Performs keyword-based document search over the corpus."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("search", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("search", request, res)
        return res

    payload = _extract_recognized_fields("search", request)
    query_str = payload["query"]
    max_results = payload.get("max_results", 10)
    page = payload.get("page", 1)
    if page < 1:
        page = 1
    filters = payload.get("filters")

    # Filter candidates by metadata criteria if supplied
    candidates = list(_CORPUS)
    if filters and isinstance(filters, dict):
        for k, v in filters.items():
            candidates = [c for c in candidates if c.get(k) == v]

    # Rank candidates by relevance score
    scored_items = []
    for doc in candidates:
        s = _score_document(query_str, doc)
        if s > 0.0:
            scored_items.append((doc, s))

    scored_items.sort(key=lambda x: x[1], reverse=True)

    total = len(scored_items)

    # 1-indexed pagination
    start_idx = (page - 1) * max_results
    end_idx = start_idx + max_results
    page_items = scored_items[start_idx:end_idx]

    formatted_results = [
        {
            "id": item[0]["id"],
            "title": item[0]["title"],
            "snippet": item[0]["snippet"],
            "score": item[1],
        }
        for item in page_items
    ]

    res = {
        "status": "success",
        "results": formatted_results,
        "total": total,
        "page": page,
    }
    _log_request("search", request, res)
    return res


def get_document(request: dict = None, **kwargs) -> dict:
    """Retrieves full document record by document_id."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_document", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("get_document", request, res)
        return res

    payload = _extract_recognized_fields("get_document", request)
    doc_id = payload["document_id"]

    for doc in _CORPUS:
        if doc["id"] == doc_id:
            res = {
                "status": "success",
                "document": copy.deepcopy(doc),
            }
            _log_request("get_document", request, res)
            return res

    res = {"status": "error", "errors": [f"Document '{doc_id}' not found"]}
    _log_request("get_document", request, res)
    return res


def get_related_documents(request: dict = None, **kwargs) -> dict:
    """Finds related documents matching the category of the target document."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_related_documents", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("get_related_documents", request, res)
        return res

    payload = _extract_recognized_fields("get_related_documents", request)
    doc_id = payload["document_id"]
    max_results = payload.get("max_results", 5)

    target_doc = None
    for doc in _CORPUS:
        if doc["id"] == doc_id:
            target_doc = doc
            break

    if not target_doc:
        res = {"status": "error", "errors": [f"Document '{doc_id}' not found"]}
        _log_request("get_related_documents", request, res)
        return res

    target_cat = target_doc.get("category")
    related = [
        {
            "id": d["id"],
            "title": d["title"],
            "snippet": d["snippet"],
            "score": 0.8 if d.get("category") == target_cat else 0.4,
        }
        for d in _CORPUS
        if d["id"] != doc_id
    ]

    related.sort(key=lambda x: x["score"], reverse=True)
    if max_results > 0:
        related = related[:max_results]

    res = {
        "status": "success",
        "results": related,
        "total": len(related),
    }
    _log_request("get_related_documents", request, res)
    return res


# 5. _inspect_ground_truth: Test-only helper returning direct copy of ground truth.
def _inspect_ground_truth() -> dict:
    """Returns a deep copy of the private ground truth state for testing."""
    return copy.deepcopy(_GROUND_TRUTH)


def _reset_ground_truth() -> None:
    """Resets the ground truth request log (test helper)."""
    _GROUND_TRUTH["request_log"] = []


# 6. Smoke test execution block.
if __name__ == "__main__":
    print("=== Search API Smoke Test ===")
    search_res = search({"query": "outdoor event guidelines"})
    print("Search Result:", search_res)

    if search_res["results"]:
        top_id = search_res["results"][0]["id"]
        doc_res = get_document({"document_id": top_id})
        print("Get Document Result:", doc_res)

        rel_res = get_related_documents({"document_id": top_id, "max_results": 2})
        print("Related Docs Result:", rel_res)

    print("Ground Truth Log Count:", len(_inspect_ground_truth()["request_log"]))
