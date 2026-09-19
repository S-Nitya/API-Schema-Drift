"""Mock Payment API tool following Stripe conventions.

Implements schema-validated customer charges, refunds, transaction lookups, and listings
with deterministic state management and ground truth tracking.

Currency convention:
- 'amount' represents major currency units as a float (e.g., 49.99 for $49.99 USD).
This convention is key for later semantic drift testing (e.g. dollars -> cents).
"""

import copy

# 1. SCHEMA: Module-level contract definition.
# Must be read at call-time (no cached copies) by _validate and handler functions.
SCHEMA = {
    "tool": "payment",
    "endpoints": {
        "charge_customer": {
            "request": {
                "customer_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the customer to charge",
                },
                "amount": {
                    "type": float,
                    "required": True,
                    "description": "Amount to charge in major currency units (e.g., 50.00 for $50.00)",
                },
                "currency": {
                    "type": str,
                    "required": False,
                    "description": "Three-letter ISO currency code (e.g., 'USD', 'INR', 'EUR')",
                },
                "description": {
                    "type": str,
                    "required": False,
                    "description": "Memo or line-item description for the charge",
                },
                "payment_method": {
                    "type": str,
                    "required": False,
                    "description": "Payment instrument identifier or type (e.g., 'card', 'bank_transfer', 'wallet')",
                },
                "metadata": {
                    "type": dict,
                    "required": False,
                    "description": "Custom metadata key-value dictionary",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "transaction_id": {"type": str, "required": True, "description": "Unique transaction charge identifier"},
                "customer_id": {"type": str, "required": True, "description": "Customer identifier charged"},
                "amount": {"type": float, "required": True, "description": "Amount charged in currency units"},
                "currency": {"type": str, "required": True, "description": "Three-letter ISO currency code"},
                "transaction_status": {"type": str, "required": True, "description": "State of transaction ('succeeded', 'failed', 'refunded')"},
                "created_at": {"type": int, "required": True, "description": "Unix epoch timestamp when charge occurred"},
            },
        },
        "refund_customer": {
            "request": {
                "transaction_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique identifier of the original transaction to refund",
                },
                "amount": {
                    "type": float,
                    "required": False,
                    "description": "Amount to refund (defaults to full remaining amount if omitted)",
                },
                "reason": {
                    "type": str,
                    "required": False,
                    "description": "Reason for refund (e.g., 'requested_by_customer', 'duplicate')",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "refund_id": {"type": str, "required": True, "description": "Unique refund identifier"},
                "transaction_id": {"type": str, "required": True, "description": "Associated original transaction identifier"},
                "amount_refunded": {"type": float, "required": True, "description": "Amount refunded in currency units"},
                "currency": {"type": str, "required": True, "description": "Currency code of the refund"},
                "created_at": {"type": int, "required": True, "description": "Unix epoch timestamp of refund"},
            },
        },
        "get_transaction": {
            "request": {
                "transaction_id": {
                    "type": str,
                    "required": True,
                    "description": "Unique transaction identifier to retrieve",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "transaction": {"type": dict, "required": False, "description": "Transaction ledger record"},
            },
        },
        "list_transactions": {
            "request": {
                "customer_id": {
                    "type": str,
                    "required": False,
                    "description": "Filter transactions by customer ID",
                },
                "limit": {
                    "type": int,
                    "required": False,
                    "description": "Maximum number of transactions to return",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "transactions": {"type": list, "required": True, "description": "List of transaction records"},
                "count": {"type": int, "required": True, "description": "Total number of transactions returned"},
            },
        },
    },
}

# 2. Ground truth state: Private dict storing actual ledger and refund records.
_GROUND_TRUTH = {
    "transactions": {},
    "refunds": {},
    "counter": 0,
    "refund_counter": 0,
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
def charge_customer(request: dict = None, **kwargs) -> dict:
    """Charges a customer for an amount in currency units."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("charge_customer", request)
    if errors:
        return {"status": "error", "errors": errors}

    # Extract schema-recognized fields
    payload = _extract_recognized_fields("charge_customer", request)
    amount = float(payload["amount"])

    if amount <= 0:
        return {"status": "error", "errors": ["Charge amount must be greater than zero"]}

    _GROUND_TRUTH["counter"] += 1
    counter = _GROUND_TRUTH["counter"]
    tx_id = f"tx_{counter:04d}"
    created_at = _GROUND_TRUTH["base_epoch"] + (counter * 60)
    currency = payload.get("currency", "USD").upper()

    tx_record = {
        "transaction_id": tx_id,
        "customer_id": payload["customer_id"],
        "amount": amount,
        "currency": currency,
        "description": payload.get("description", ""),
        "payment_method": payload.get("payment_method", "card"),
        "transaction_status": "succeeded",
        "refunded_amount": 0.0,
        "created_at": created_at,
        "metadata": payload.get("metadata", {}),
    }
    _GROUND_TRUTH["transactions"][tx_id] = copy.deepcopy(tx_record)

    return {
        "status": "success",
        "transaction_id": tx_id,
        "customer_id": payload["customer_id"],
        "amount": amount,
        "currency": currency,
        "transaction_status": "succeeded",
        "created_at": created_at,
    }


def refund_customer(request: dict = None, **kwargs) -> dict:
    """Refunds a previous transaction partially or in full."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("refund_customer", request)
    if errors:
        return {"status": "error", "errors": errors}

    payload = _extract_recognized_fields("refund_customer", request)
    tx_id = payload["transaction_id"]

    if tx_id not in _GROUND_TRUTH["transactions"]:
        return {"status": "error", "errors": [f"Transaction '{tx_id}' not found"]}

    tx_record = _GROUND_TRUTH["transactions"][tx_id]
    original_amount = tx_record["amount"]
    already_refunded = tx_record["refunded_amount"]
    refundable_balance = round(original_amount - already_refunded, 4)

    if refundable_balance <= 0:
        return {"status": "error", "errors": [f"Transaction '{tx_id}' is already fully refunded"]}

    refund_amount = payload.get("amount")
    if refund_amount is None:
        refund_amount = refundable_balance
    else:
        refund_amount = float(refund_amount)

    if refund_amount <= 0:
        return {"status": "error", "errors": ["Refund amount must be greater than zero"]}

    if refund_amount > refundable_balance:
        return {
            "status": "error",
            "errors": [
                f"Refund amount {refund_amount} exceeds refundable balance {refundable_balance}"
            ],
        }

    _GROUND_TRUTH["refund_counter"] += 1
    refund_counter = _GROUND_TRUTH["refund_counter"]
    refund_id = f"ref_{refund_counter:04d}"
    created_at = _GROUND_TRUTH["base_epoch"] + (refund_counter * 60)

    # Mutate ground truth
    tx_record["refunded_amount"] = round(already_refunded + refund_amount, 4)
    if tx_record["refunded_amount"] >= original_amount:
        tx_record["transaction_status"] = "refunded"
    else:
        tx_record["transaction_status"] = "partially_refunded"

    refund_record = {
        "refund_id": refund_id,
        "transaction_id": tx_id,
        "amount_refunded": refund_amount,
        "currency": tx_record["currency"],
        "reason": payload.get("reason", "requested_by_customer"),
        "created_at": created_at,
    }
    _GROUND_TRUTH["refunds"][refund_id] = copy.deepcopy(refund_record)

    return {
        "status": "success",
        "refund_id": refund_id,
        "transaction_id": tx_id,
        "amount_refunded": refund_amount,
        "currency": tx_record["currency"],
        "created_at": created_at,
    }


def get_transaction(request: dict = None, **kwargs) -> dict:
    """Retrieves a transaction record by transaction_id."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_transaction", request)
    if errors:
        return {"status": "error", "errors": errors}

    tx_id = request["transaction_id"]
    if tx_id in _GROUND_TRUTH["transactions"]:
        return {
            "status": "success",
            "transaction": copy.deepcopy(_GROUND_TRUTH["transactions"][tx_id]),
        }

    return {"status": "error", "errors": [f"Transaction '{tx_id}' not found"]}


def list_transactions(request: dict = None, **kwargs) -> dict:
    """Lists transactions with optional filtering by customer ID and limit."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("list_transactions", request)
    if errors:
        return {"status": "error", "errors": errors}

    results = list(_GROUND_TRUTH["transactions"].values())

    cust_filter = request.get("customer_id")
    if cust_filter:
        results = [t for t in results if t.get("customer_id") == cust_filter]

    limit = request.get("limit")
    if limit is not None and limit > 0:
        results = results[:limit]

    return {
        "status": "success",
        "transactions": copy.deepcopy(results),
        "count": len(results),
    }


# 5. _inspect_ground_truth: Test-only helper returning direct copy of ground truth.
def _inspect_ground_truth() -> dict:
    """Returns a deep copy of the private ground truth state for testing."""
    return copy.deepcopy(_GROUND_TRUTH)


def _reset_ground_truth() -> None:
    """Resets the ground truth state to initial empty state (test helper)."""
    _GROUND_TRUTH["transactions"] = {}
    _GROUND_TRUTH["refunds"] = {}
    _GROUND_TRUTH["counter"] = 0
    _GROUND_TRUTH["refund_counter"] = 0
    _GROUND_TRUTH["base_epoch"] = 1700000000


# 6. Smoke test execution block.
if __name__ == "__main__":
    print("=== Payment API Smoke Test ===")
    charge_req = {
        "customer_id": "cust_0001",
        "amount": 99.50,
        "currency": "USD",
        "description": "Annual Premium Subscription",
        "payment_method": "card",
        "metadata": {"plan": "premium_annual"},
        "extra_unrecognized_field": "should_be_ignored",
    }

    charge_res = charge_customer(charge_req)
    print("Charge Customer Result:", charge_res)

    tx_id = charge_res["transaction_id"]

    get_res = get_transaction({"transaction_id": tx_id})
    print("Get Transaction Result:", get_res)

    refund_res = refund_customer({"transaction_id": tx_id, "amount": 20.00, "reason": "partial_discount"})
    print("Refund Result:", refund_res)

    list_res = list_transactions({"customer_id": "cust_0001"})
    print("List Transactions Result:", list_res)

    print("\nGround Truth State:", _inspect_ground_truth())
