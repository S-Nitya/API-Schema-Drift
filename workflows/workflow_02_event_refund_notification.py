"""Workflow 02: Event Refund Notification.

API Sequence: Search (search) -> Payment (refund_customer) -> Email (send_email)
Stakes: High
Description: Process weather-triggered outdoor event ticket refund and notify attendee.
"""

from typing import Any, Dict, Optional
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api


def run_workflow_02(
    query: str = "Event Cancellation Refund Policy",
    attendee_email: str = "attendee.raj@example.com",
    transaction_id: Optional[str] = None,
    refund_amount: float = 75.0,
    currency: str = "USD",
    reason: str = "weather_cancellation",
) -> Dict[str, Any]:
    """Executes Workflow 02: Search -> Payment -> Email."""
    steps = []
    errors = []

    # Step 1: Search knowledge base for refund policy
    search_req = {
        "query": query,
        "max_results": 3,
    }
    search_res = search_api.search(search_req)
    steps.append({
        "step_index": 1,
        "tool": "search",
        "endpoint": "search",
        "request": search_req,
        "response": search_res,
    })
    if search_res.get("status") != "success":
        errors.extend(search_res.get("errors", ["Search failed"]))
        return {
            "workflow_id": "W02",
            "workflow_name": "Process weather-triggered outdoor event ticket refund and notify attendee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Prerequisite: ensure an active transaction exists if none passed
    if transaction_id is None:
        charge_res = payment_api.charge_customer({
            "customer_id": "cust_temp_002",
            "amount": refund_amount,
            "currency": currency,
            "description": "General Admission Ticket",
        })
        if charge_res.get("status") == "success":
            transaction_id = charge_res["transaction_id"]
        else:
            transaction_id = "tx_0001"

    # Step 2: Payment refund_customer
    pay_req = {
        "transaction_id": transaction_id,
        "amount": refund_amount,
        "reason": reason,
    }
    pay_res = payment_api.refund_customer(pay_req)
    steps.append({
        "step_index": 2,
        "tool": "payment",
        "endpoint": "refund_customer",
        "request": pay_req,
        "response": pay_res,
    })
    if pay_res.get("status") != "success":
        errors.extend(pay_res.get("errors", ["Payment refund failed"]))
        return {
            "workflow_id": "W02",
            "workflow_name": "Process weather-triggered outdoor event ticket refund and notify attendee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"transaction_id": transaction_id},
            "errors": errors,
        }

    refund_id = pay_res["refund_id"]
    amount_refunded = pay_res.get("amount_refunded", refund_amount)

    # Step 3: Email send_email
    email_req = {
        "to": attendee_email,
        "subject": "Event Cancellation: Ticket Refund Confirmation",
        "body": (
            f"Dear Attendee, in accordance with our Event Cancellation Policy, your ticket payment "
            f"has been refunded in full. Refund ID: {refund_id}, Original Tx: {transaction_id}, "
            f"Amount: {currency} {amount_refunded:.2f}."
        ),
        "sender": {
            "email": "support@events.org",
            "name": "Event Support Desk",
        },
    }
    email_res = email_api.send_email(email_req)
    steps.append({
        "step_index": 3,
        "tool": "email",
        "endpoint": "send_email",
        "request": email_req,
        "response": email_res,
    })
    if email_res.get("status") != "success":
        errors.extend(email_res.get("errors", ["Email dispatch failed"]))
        return {
            "workflow_id": "W02",
            "workflow_name": "Process weather-triggered outdoor event ticket refund and notify attendee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {
                "transaction_id": transaction_id,
                "refund_id": refund_id,
            },
            "errors": errors,
        }

    message_id = email_res["message_id"]

    return {
        "workflow_id": "W02",
        "workflow_name": "Process weather-triggered outdoor event ticket refund and notify attendee",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "transaction_id": transaction_id,
            "refund_id": refund_id,
            "message_id": message_id,
            "amount_refunded": amount_refunded,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_02()
    print("Workflow 02 Result:", result)
