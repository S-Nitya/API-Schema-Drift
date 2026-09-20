"""Workflow 10: Customer Billing Audit and Transaction Verification.

API Sequence: Email (list_emails) -> CRM (get_customer) -> Payment (get_transaction)
Stakes: Low
Description: Audit customer communication history, fetch account profile, and verify transaction receipt.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api


def run_workflow_10(
    customer_email: str = "audit.client@example.com",
    customer_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
    amount: float = 150.0,
) -> Dict[str, Any]:
    """Executes Workflow 10: Email -> CRM -> Payment."""
    steps = []
    errors = []

    # Prerequisite setup if called with clean/empty ground truth
    if customer_id is None:
        crm_create = crm_api.create_customer({
            "name": "Audit Client User",
            "email": customer_email,
            "phone": "+91-9876500000",
            "company": "Audit Services Corp",
            "status": "active",
        })
        customer_id = crm_create.get("customer_id", "cust_0010")

    if transaction_id is None:
        pay_charge = payment_api.charge_customer({
            "customer_id": customer_id,
            "amount": amount,
            "currency": "USD",
            "description": "Standard Conference Pass",
        })
        transaction_id = pay_charge.get("transaction_id", "tx_0010")

    # Step 1: Email list_emails (audit recent dispatches for missing billing messages)
    list_req = {
        "to": customer_email,
        "limit": 5,
    }
    list_res = email_api.list_emails(list_req)
    steps.append({
        "step_index": 1,
        "tool": "email",
        "endpoint": "list_emails",
        "request": list_req,
        "response": list_res,
    })
    if list_res.get("status") != "success":
        errors.extend(list_res.get("errors", ["Email listing failed"]))
        return {
            "workflow_id": "W10",
            "workflow_name": "Audit customer communication history, fetch account profile, and verify transaction receipt",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: CRM get_customer
    crm_req = {
        "customer_id": customer_id,
    }
    crm_res = crm_api.get_customer(crm_req)
    steps.append({
        "step_index": 2,
        "tool": "crm",
        "endpoint": "get_customer",
        "request": crm_req,
        "response": crm_res,
    })
    if crm_res.get("status") != "success":
        errors.extend(crm_res.get("errors", ["Customer lookup failed"]))
        return {
            "workflow_id": "W10",
            "workflow_name": "Audit customer communication history, fetch account profile, and verify transaction receipt",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 3: Payment get_transaction
    pay_req = {
        "transaction_id": transaction_id,
    }
    pay_res = payment_api.get_transaction(pay_req)
    steps.append({
        "step_index": 3,
        "tool": "payment",
        "endpoint": "get_transaction",
        "request": pay_req,
        "response": pay_res,
    })
    if pay_res.get("status") != "success":
        errors.extend(pay_res.get("errors", ["Transaction retrieval failed"]))
        return {
            "workflow_id": "W10",
            "workflow_name": "Audit customer communication history, fetch account profile, and verify transaction receipt",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {
                "customer_id": customer_id,
            },
            "errors": errors,
        }

    return {
        "workflow_id": "W10",
        "workflow_name": "Audit customer communication history, fetch account profile, and verify transaction receipt",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "customer_record": crm_res.get("customer", {}),
            "transaction_record": pay_res.get("transaction", {}),
            "email_count": len(list_res.get("emails", [])),
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_10()
    print("Workflow 10 Result:", result)
