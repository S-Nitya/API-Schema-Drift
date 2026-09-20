"""Workflow 05: Cancellation Email Audit and Ticket Refund.

API Sequence: Email (list_emails) -> CRM (get_customer) -> Payment (refund_customer)
Stakes: High
Description: Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api


def run_workflow_05(
    attendee_email: str = "attendee.priya@example.com",
    customer_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
    refund_amount: float = 75.0,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Executes Workflow 05: Email -> CRM -> Payment."""
    steps = []
    errors = []

    # Prerequisite setup if called with clean/empty ground truth
    if customer_id is None:
        crm_create = crm_api.create_customer({
            "name": "Priya Sharma",
            "email": attendee_email,
            "phone": "+91-9876543210",
            "company": "TechSummit Attendee",
            "status": "active",
        })
        customer_id = crm_create.get("customer_id", "cust_0005")

    if transaction_id is None:
        pay_charge = payment_api.charge_customer({
            "customer_id": customer_id,
            "amount": refund_amount,
            "currency": currency,
            "description": "Standard Event Ticket Pass",
        })
        transaction_id = pay_charge.get("transaction_id", "tx_0005")

    # Step 1: Email list_emails (inspect communications history for cancellation inquiries)
    email_list_req = {
        "to": attendee_email,
        "limit": 5,
    }
    email_list_res = email_api.list_emails(email_list_req)
    steps.append({
        "step_index": 1,
        "tool": "email",
        "endpoint": "list_emails",
        "request": email_list_req,
        "response": email_list_res,
    })
    if email_list_res.get("status") != "success":
        errors.extend(email_list_res.get("errors", ["Email listing failed"]))
        return {
            "workflow_id": "W05",
            "workflow_name": "Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: CRM get_customer
    crm_get_req = {
        "customer_id": customer_id,
    }
    crm_get_res = crm_api.get_customer(crm_get_req)
    steps.append({
        "step_index": 2,
        "tool": "crm",
        "endpoint": "get_customer",
        "request": crm_get_req,
        "response": crm_get_res,
    })
    if crm_get_res.get("status") != "success":
        errors.extend(crm_get_res.get("errors", ["Customer lookup failed"]))
        return {
            "workflow_id": "W05",
            "workflow_name": "Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 3: Payment refund_customer
    refund_req = {
        "transaction_id": transaction_id,
        "amount": refund_amount,
        "reason": "cancellation_requested_via_email",
    }
    refund_res = payment_api.refund_customer(refund_req)
    steps.append({
        "step_index": 3,
        "tool": "payment",
        "endpoint": "refund_customer",
        "request": refund_req,
        "response": refund_res,
    })
    if refund_res.get("status") != "success":
        errors.extend(refund_res.get("errors", ["Refund processing failed"]))
        return {
            "workflow_id": "W05",
            "workflow_name": "Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {
                "customer_id": customer_id,
                "transaction_id": transaction_id,
            },
            "errors": errors,
        }

    refund_id = refund_res["refund_id"]
    amount_refunded = refund_res.get("amount_refunded", refund_amount)

    return {
        "workflow_id": "W05",
        "workflow_name": "Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "refund_id": refund_id,
            "amount_refunded": amount_refunded,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_05()
    print("Workflow 05 Result:", result)
