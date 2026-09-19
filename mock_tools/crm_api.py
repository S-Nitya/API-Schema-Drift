"""Mock CRM API tool following Salesforce / HubSpot conventions.

Implements schema-validated customer creation, update, retrieval, and listing operations
with deterministic state management and ground truth tracking.
"""

import copy

# 1. SCHEMA: Module-level contract definition.
# Must be read at call-time (no cached copies) by _validate and handler functions.
SCHEMA = {
    "tool": "crm",
    "endpoints": {
        "create_customer": {
            "request": {
                "name": {
                    "type": str,
                    "required": True,
                    "description": "Full name of the customer",
                },
                "email": {
                    "type": str,
                    "required": True,
                    "description": "Primary email address of the customer",
                },
                "phone": {
                    "type": str,
                    "required": False,
                    "description": "Contact phone number with country code",
                },
                "company": {
                    "type": str,
                    "required": False,
                    "description": "Company or organization affiliation",
                },
                "status": {
                    "type": str,
                    "required": False,
                    "description": "Customer lifecycle status (e.g. 'active', 'lead', 'prospect', 'churned')",
                },
                "address": {
                    "type": dict,
                    "required": False,
                    "description": "Customer physical/billing address object",
                    "properties": {
                        "street": {"type": str, "required": False, "description": "Street address"},
                        "city": {"type": str, "required": False, "description": "City name"},
                        "country": {"type": str, "required": False, "description": "Country name or ISO code"},
                        "postal_code": {"type": str, "required": False, "description": "Postal/ZIP code"},
                    },
                },
                "metadata": {
                    "type": dict,
                    "required": False,
                    "description": "Custom metadata key-value dictionary",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "customer_id": {"type": str, "required": True, "description": "Unique CRM customer identifier"},
                "created_at": {"type": int, "required": True, "description": "Unix epoch timestamp when customer was created"},
            },
        },
        "update_customer": {
            "request": {
                "customer_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the customer to update",
                },
                "name": {
                    "type": str,
                    "required": False,
                    "description": "Updated full name of the customer",
                },
                "email": {
                    "type": str,
                    "required": False,
                    "description": "Updated primary email address",
                },
                "phone": {
                    "type": str,
                    "required": False,
                    "description": "Updated contact phone number",
                },
                "company": {
                    "type": str,
                    "required": False,
                    "description": "Updated company or organization name",
                },
                "status": {
                    "type": str,
                    "required": False,
                    "description": "Updated customer lifecycle status",
                },
                "address": {
                    "type": dict,
                    "required": False,
                    "description": "Updated customer address object",
                    "properties": {
                        "street": {"type": str, "required": False, "description": "Street address"},
                        "city": {"type": str, "required": False, "description": "City name"},
                        "country": {"type": str, "required": False, "description": "Country name or ISO code"},
                        "postal_code": {"type": str, "required": False, "description": "Postal/ZIP code"},
                    },
                },
                "metadata": {
                    "type": dict,
                    "required": False,
                    "description": "Updated custom metadata key-value dictionary",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "customer_id": {"type": str, "required": True, "description": "Unique customer identifier"},
                "updated_at": {"type": int, "required": True, "description": "Unix epoch timestamp of update"},
            },
        },
        "get_customer": {
            "request": {
                "customer_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique customer identifier to look up",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "customer": {"type": dict, "required": False, "description": "Customer record object"},
            },
        },
        "list_customers": {
            "request": {
                "status": {
                    "type": str,
                    "required": False,
                    "description": "Filter customers by lifecycle status",
                },
                "limit": {
                    "type": int,
                    "required": False,
                    "description": "Maximum number of records to return",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "customers": {"type": list, "required": True, "description": "List of customer record objects"},
                "count": {"type": int, "required": True, "description": "Total number of records returned"},
            },
        },
    },
}

# 2. Ground truth state: Private dict storing actual stored customers.
_GROUND_TRUTH = {
    "customers": {},
    "counter": 0,
    "base_epoch": 1700000000,
}


# 3. _validate: Schema validation engine reading SCHEMA at call time.
def _validate(endpoint: str, request: dict) -> list[str]:
    """Validates a request dictionary against the live SCHEMA definition at call time."""
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

        # Strict type checking (bool is not treated as int or float)
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
def create_customer(request: dict = None, **kwargs) -> dict:
    """Creates a new customer record in CRM."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("create_customer", request)
    if errors:
        return {"status": "error", "errors": errors}

    _GROUND_TRUTH["counter"] += 1
    counter = _GROUND_TRUTH["counter"]
    customer_id = f"cust_{counter:04d}"
    created_at = _GROUND_TRUTH["base_epoch"] + (counter * 60)

    # Store only schema-recognized fields in ground truth
    payload = _extract_recognized_fields("create_customer", request)
    customer_record = {
        "customer_id": customer_id,
        "created_at": created_at,
        "updated_at": created_at,
        "status": payload.get("status", "active"),
        **payload,
    }
    _GROUND_TRUTH["customers"][customer_id] = copy.deepcopy(customer_record)

    return {
        "status": "success",
        "customer_id": customer_id,
        "created_at": created_at,
    }


def update_customer(request: dict = None, **kwargs) -> dict:
    """Updates an existing customer record in CRM."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("update_customer", request)
    if errors:
        return {"status": "error", "errors": errors}

    customer_id = request["customer_id"]
    if customer_id not in _GROUND_TRUTH["customers"]:
        return {"status": "error", "errors": [f"Customer '{customer_id}' not found"]}

    _GROUND_TRUTH["counter"] += 1
    counter = _GROUND_TRUTH["counter"]
    updated_at = _GROUND_TRUTH["base_epoch"] + (counter * 60)

    payload = _extract_recognized_fields("update_customer", request)
    # Remove customer_id from fields to update
    payload.pop("customer_id", None)

    current_record = _GROUND_TRUTH["customers"][customer_id]
    current_record.update(copy.deepcopy(payload))
    current_record["updated_at"] = updated_at

    return {
        "status": "success",
        "customer_id": customer_id,
        "updated_at": updated_at,
    }


def get_customer(request: dict = None, **kwargs) -> dict:
    """Retrieves a customer record by customer_id."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_customer", request)
    if errors:
        return {"status": "error", "errors": errors}

    customer_id = request["customer_id"]
    if customer_id in _GROUND_TRUTH["customers"]:
        return {
            "status": "success",
            "customer": copy.deepcopy(_GROUND_TRUTH["customers"][customer_id]),
        }

    return {"status": "error", "errors": [f"Customer '{customer_id}' not found"]}


def list_customers(request: dict = None, **kwargs) -> dict:
    """Lists customers with optional status filtering and limit."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("list_customers", request)
    if errors:
        return {"status": "error", "errors": errors}

    results = list(_GROUND_TRUTH["customers"].values())

    status_filter = request.get("status")
    if status_filter:
        results = [c for c in results if c.get("status") == status_filter]

    limit = request.get("limit")
    if limit is not None and limit > 0:
        results = results[:limit]

    return {
        "status": "success",
        "customers": copy.deepcopy(results),
        "count": len(results),
    }


# 5. _inspect_ground_truth: Test-only helper returning direct copy of ground truth.
def _inspect_ground_truth() -> dict:
    """Returns a deep copy of the private ground truth state for testing."""
    return copy.deepcopy(_GROUND_TRUTH)


def _reset_ground_truth() -> None:
    """Resets the ground truth state to initial empty state (test helper)."""
    _GROUND_TRUTH["customers"] = {}
    _GROUND_TRUTH["counter"] = 0
    _GROUND_TRUTH["base_epoch"] = 1700000000


# 6. Smoke test execution block.
if __name__ == "__main__":
    print("=== CRM API Smoke Test ===")
    create_req = {
        "name": "Rahul Sharma",
        "email": "rahul.sharma@example.com",
        "phone": "+91-9876543210",
        "company": "Acme Corp",
        "status": "active",
        "address": {
            "street": "123 MG Road",
            "city": "Bengaluru",
            "country": "India",
            "postal_code": "560001",
        },
        "metadata": {"tier": "gold"},
        "extra_unrecognized_field": "should_be_ignored",
    }

    create_res = create_customer(create_req)
    print("Create Customer Result:", create_res)

    cust_id = create_res["customer_id"]

    update_res = update_customer({"customer_id": cust_id, "status": "premium"})
    print("Update Customer Result:", update_res)

    get_res = get_customer({"customer_id": cust_id})
    print("Get Customer Result:", get_res)

    list_res = list_customers({"status": "premium"})
    print("List Customers Result:", list_res)

    print("\nGround Truth State:", _inspect_ground_truth())
