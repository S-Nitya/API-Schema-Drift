"""Workflow 12: Sponsor Booth Booking, Charge, and Delivery Verification.

API Sequence: CRM (get_customer) -> Payment (charge_customer) -> Email (send_email) -> Email (get_email)
Stakes: High
Description: Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api


def run_workflow_12(
    customer_id: Optional[str] = None,
    sponsor_email: str = "booths@innovatecorp.com",
    booth_fee: float = 350.0,
    currency: str = "USD",
    payment_method: str = "card",
    cc_emails: Optional[list] = None,
    send_at: Optional[int] = 1700007200,
) -> Dict[str, Any]:
    """Executes Workflow 12: CRM -> Payment -> Email -> Email."""
    if cc_emails is None:
        cc_emails = ["events@innovatecorp.com"]

    steps = []
    errors = []

    # Prerequisite setup if called with clean/empty ground truth
    if customer_id is None:
        crm_create = crm_api.create_customer({
            "name": "Innovate Corp Sponsor",
            "email": sponsor_email,
            "phone": "+91-9888877777",
            "company": "Innovate Corp",
            "status": "active",
        })
        customer_id = crm_create.get("customer_id", "cust_0012")

    # Step 1: CRM get_customer
    crm_req = {
        "customer_id": customer_id,
    }
    crm_res = crm_api.get_customer(crm_req)
    steps.append({
        "step_index": 1,
        "tool": "crm",
        "endpoint": "get_customer",
        "request": crm_req,
        "response": crm_res,
    })
    if crm_res.get("status") != "success":
        errors.extend(crm_res.get("errors", ["Customer lookup failed"]))
        return {
            "workflow_id": "W12",
            "workflow_name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: Payment charge_customer
    pay_req = {
        "customer_id": customer_id,
        "amount": booth_fee,
        "currency": currency,
        "description": "Exhibition Booth #B-14 Reservation Fee",
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
            "workflow_id": "W12",
            "workflow_name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"customer_id": customer_id},
            "errors": errors,
        }

    transaction_id = pay_res["transaction_id"]

    # Step 3: Email send_email
    email_req = {
        "to": sponsor_email,
        "subject": "Confirmed: Exhibition Booth Reservation and Receipt",
        "body": (
            f"Dear Sponsor, Your booth reservation is confirmed. Charged: {currency} {booth_fee:.2f} "
            f"(Transaction: {transaction_id}). Setup access opens at 08:00 AM on event day."
        ),
        "cc": cc_emails,
        "send_at": send_at,
        "sender": {
            "email": "exhibitions@events.org",
            "name": "Exhibitions & Booths Team",
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
            "workflow_id": "W12",
            "workflow_name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
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

    # Step 4: Email get_email
    get_email_req = {
        "message_id": message_id,
    }
    get_email_res = email_api.get_email(get_email_req)
    steps.append({
        "step_index": 4,
        "tool": "email",
        "endpoint": "get_email",
        "request": get_email_req,
        "response": get_email_res,
    })
    if get_email_res.get("status") != "success":
        errors.extend(get_email_res.get("errors", ["Email verification failed"]))
        return {
            "workflow_id": "W12",
            "workflow_name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {
                "customer_id": customer_id,
                "transaction_id": transaction_id,
                "message_id": message_id,
            },
            "errors": errors,
        }

    return {
        "workflow_id": "W12",
        "workflow_name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "message_id": message_id,
            "email_status": get_email_res.get("email", {}).get("status", "sent"),
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_12()
    print("Workflow 12 Result:", result)
