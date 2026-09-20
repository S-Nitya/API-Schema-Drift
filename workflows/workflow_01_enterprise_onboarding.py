"""Workflow 01: Enterprise Client Onboarding.

API Sequence: CRM (create_customer) -> Payment (charge_customer) -> Email (send_email)
Stakes: High
Description: Onboard a new enterprise sponsor, charge setup fee, and send itemized invoice receipt.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api


def run_workflow_01(
    name: str = "Acme Corp",
    email: str = "billing@acme.com",
    phone: str = "+1-555-0199",
    company: str = "Acme Corporation",
    address: Optional[Dict[str, str]] = None,
    amount: float = 500.0,
    currency: str = "USD",
    payment_method: str = "card",
    cc_emails: Optional[list] = None,
) -> Dict[str, Any]:
    """Executes Workflow 01: CRM -> Payment -> Email."""
    if address is None:
        address = {
            "street": "100 Innovation Way",
            "city": "Bengaluru",
            "country": "IN",
            "postal_code": "560001",
        }
    if cc_emails is None:
        cc_emails = ["finance@acme.com"]

    steps = []
    errors = []

    # Step 1: CRM create_customer
    crm_req = {
        "name": name,
        "email": email,
        "phone": phone,
        "company": company,
        "status": "active",
        "address": address,
    }
    crm_res = crm_api.create_customer(crm_req)
    steps.append({
        "step_index": 1,
        "tool": "crm",
        "endpoint": "create_customer",
        "request": crm_req,
        "response": crm_res,
    })
    if crm_res.get("status") != "success":
        errors.extend(crm_res.get("errors", ["CRM customer creation failed"]))
        return {
            "workflow_id": "W01",
            "workflow_name": "Onboard new enterprise client, charge setup fee, and send itemized invoice receipt",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    customer_id = crm_res["customer_id"]

    # Step 2: Payment charge_customer
    pay_req = {
        "customer_id": customer_id,
        "amount": amount,
        "currency": currency,
        "description": "Enterprise Onboarding Setup Fee",
        "payment_method": payment_method,
    }
    pay_res = payment_api.charge_customer(pay_req)
    steps.append({
        "step_index": 2,
        "tool": "payment",
        "endpoint": "charge_customer",
        "request": pay_req,
        "response": pay_res,
    })
    if pay_res.get("status") != "success":
        errors.extend(pay_res.get("errors", ["Payment charge failed"]))
        return {
            "workflow_id": "W01",
            "workflow_name": "Onboard new enterprise client, charge setup fee, and send itemized invoice receipt",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"customer_id": customer_id},
            "errors": errors,
        }

    transaction_id = pay_res["transaction_id"]

    # Step 3: Email send_email
    email_req = {
        "to": email,
        "subject": "Welcome to Enterprise Sponsorship - Invoice Receipt",
        "body": f"Hello {name}, your account ({customer_id}) is active. We successfully processed your setup fee of {currency} {amount:.2f} (Tx: {transaction_id}).",
        "cc": cc_emails,
        "sender": {
            "email": "accounts@events.org",
            "name": "Event Accounts Desk",
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
            "workflow_id": "W01",
            "workflow_name": "Onboard new enterprise client, charge setup fee, and send itemized invoice receipt",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {
                "customer_id": customer_id,
                "transaction_id": transaction_id,
            },
            "errors": errors,
        }

    message_id = email_res["message_id"]

    return {
        "workflow_id": "W01",
        "workflow_name": "Onboard new enterprise client, charge setup fee, and send itemized invoice receipt",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "message_id": message_id,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_01()
    print("Workflow 01 Result:", result)
