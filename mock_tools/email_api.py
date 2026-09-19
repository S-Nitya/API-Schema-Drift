"""Mock Email API tool following SendGrid/Mailgun conventions.

Implements schema-validated email dispatch, retrieval, and listing operations
with deterministic state management and ground truth tracking.
"""

import copy

# 1. SCHEMA: Module-level contract definition.
# Must be read at call-time (no cached copies) by _validate and handler functions.
SCHEMA = {
    "tool": "email",
    "endpoints": {
        "send_email": {
            "request": {
                "to": {
                    "type": str,
                    "required": True,
                    "description": "Primary recipient email address",
                },
                "subject": {
                    "type": str,
                    "required": True,
                    "description": "Subject line of the email",
                },
                "body": {
                    "type": str,
                    "required": True,
                    "description": "Text body content of the email",
                },
                "cc": {
                    "type": list,
                    "required": False,
                    "description": "List of CC recipient email addresses",
                },
                "send_at": {
                    "type": int,
                    "required": False,
                    "description": "Scheduled send timestamp in Unix epoch seconds",
                },
                "sender": {
                    "type": dict,
                    "required": False,
                    "description": "Sender information object containing email and name",
                    "properties": {
                        "email": {"type": str, "required": True, "description": "Sender email address"},
                        "name": {"type": str, "required": False, "description": "Sender display name"},
                    },
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "message_id": {"type": str, "required": True, "description": "Unique message identifier"},
                "queued_at": {"type": int, "required": True, "description": "Unix epoch timestamp when email was queued"},
            },
        },
        "get_email": {
            "request": {
                "message_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the message to retrieve",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "email": {"type": dict, "required": False, "description": "Email record object"},
            },
        },
        "list_emails": {
            "request": {
                "to": {
                    "type": str,
                    "required": False,
                    "description": "Filter emails by recipient email address",
                },
                "limit": {
                    "type": int,
                    "required": False,
                    "description": "Maximum number of email records to return",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "emails": {"type": list, "required": True, "description": "List of email objects"},
                "count": {"type": int, "required": True, "description": "Total number of matching emails returned"},
            },
        },
    },
}

# 2. Ground truth state: Private dict storing actual queued messages.
_GROUND_TRUTH = {
    "outbox": [],
    "counter": 0,
    "base_epoch": 1700000000,
}


# 3. _validate: Schema validation engine reading SCHEMA at call time.
def _validate(endpoint: str, request: dict) -> list[str]:
    """Validates a request dictionary against the live SCHEMA definition."""
    errors = []
    if not isinstance(request, dict):
        return ["Request must be a dictionary"]

    # Read live SCHEMA at call time
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

        # Type checking rules (strictly treat bool as not int or float)
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
            else:
                properties = field_def.get("properties", {})
                for p_name, p_def in properties.items():
                    p_type = p_def.get("type")
                    p_req = p_def.get("required", False)
                    if p_name not in val or val[p_name] is None:
                        if p_req:
                            errors.append(f"Field '{field_name}.{p_name}' is required")
                        continue
                    p_val = val[p_name]
                    if p_type is str and not isinstance(p_val, str):
                        errors.append(f"Field '{field_name}.{p_name}' must be of type str, got {type(p_val).__name__}")
                    elif p_type is int and (isinstance(p_val, bool) or not isinstance(p_val, int)):
                        errors.append(f"Field '{field_name}.{p_name}' must be of type int, got {type(p_val).__name__}")
        elif expected_type is bool:
            if not isinstance(val, bool):
                errors.append(f"Field '{field_name}' must be of type bool, got {type(val).__name__}")

    return errors


def _extract_recognized_fields(endpoint: str, request: dict) -> dict:
    """Extracts only fields recognized by the current SCHEMA endpoint definition."""
    req_schema = SCHEMA.get("endpoints", {}).get(endpoint, {}).get("request", {})
    extracted = {}
    for field_name in req_schema:
        if field_name in request and request[field_name] is not None:
            extracted[field_name] = request[field_name]
    return extracted


# 4. Handler functions: Validate request, mutate ground truth, return status.
def send_email(request: dict = None, **kwargs) -> dict:
    """Sends/queues an email message."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("send_email", request)
    if errors:
        return {"status": "error", "errors": errors}

    # Generate deterministic ID and timestamp
    _GROUND_TRUTH["counter"] += 1
    counter = _GROUND_TRUTH["counter"]
    msg_id = f"msg_{counter:04d}"
    queued_at = _GROUND_TRUTH["base_epoch"] + (counter * 60)

    # Store only schema-recognized fields in ground truth outbox
    payload = _extract_recognized_fields("send_email", request)
    stored_record = {
        "message_id": msg_id,
        "queued_at": queued_at,
        **payload,
    }
    _GROUND_TRUTH["outbox"].append(stored_record)

    return {
        "status": "success",
        "message_id": msg_id,
        "queued_at": queued_at,
    }


def get_email(request: dict = None, **kwargs) -> dict:
    """Retrieves an email message by message_id."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_email", request)
    if errors:
        return {"status": "error", "errors": errors}

    msg_id = request["message_id"]
    for record in _GROUND_TRUTH["outbox"]:
        if record["message_id"] == msg_id:
            return {
                "status": "success",
                "email": copy.deepcopy(record),
            }

    return {"status": "error", "errors": [f"Message '{msg_id}' not found"]}


def list_emails(request: dict = None, **kwargs) -> dict:
    """Lists queued emails with optional filtering by recipient and limit."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("list_emails", request)
    if errors:
        return {"status": "error", "errors": errors}

    results = list(_GROUND_TRUTH["outbox"])

    to_filter = request.get("to")
    if to_filter:
        results = [m for m in results if m.get("to") == to_filter]

    limit = request.get("limit")
    if limit is not None and limit > 0:
        results = results[:limit]

    return {
        "status": "success",
        "emails": copy.deepcopy(results),
        "count": len(results),
    }


# 5. _inspect_ground_truth: Test-only helper returning direct copy of ground truth.
def _inspect_ground_truth() -> dict:
    """Returns a deep copy of the private ground truth state for testing."""
    return copy.deepcopy(_GROUND_TRUTH)


# 6. Smoke test execution block.
if __name__ == "__main__":
    print("=== Email API Smoke Test ===")
    test_req = {
        "to": "user@example.com",
        "subject": "Welcome!",
        "body": "Thank you for registering.",
        "cc": ["manager@example.com"],
        "sender": {"email": "noreply@company.com", "name": "Company HQ"},
        "extra_unrecognized_field": "ignored_value",
    }

    res = send_email(test_req)
    print("Send Result:", res)

    get_res = get_email({"message_id": res["message_id"]})
    print("Get Result:", get_res)

    list_res = list_emails({})
    print("List Result:", list_res)

    print("Ground Truth State:", _inspect_ground_truth())
