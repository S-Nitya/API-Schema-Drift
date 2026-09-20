"""Workflow 08: Customer Profile Address Update and Email Verification.

API Sequence: CRM (update_customer) -> Email (send_email) -> Email (get_email)
Stakes: Low
Description: Update customer contact profile with new address, send confirmation email, and verify queued dispatch.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api


def run_workflow_08(
    customer_id: Optional[str] = None,
    customer_email: str = "kavita.patel@example.com",
    new_phone: str = "+91-9123456789",
    new_address: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Executes Workflow 08: CRM -> Email -> Email."""
    if new_address is None:
        new_address = {
            "street": "77 Brigade Road",
            "city": "Bengaluru",
            "country": "IN",
            "postal_code": "560025",
        }

    steps = []
    errors = []

    # Prerequisite setup if called with clean/empty ground truth
    if customer_id is None:
        crm_create = crm_api.create_customer({
            "name": "Kavita Patel",
            "email": customer_email,
            "phone": "+91-9000000000",
            "company": "Patel Consulting",
            "status": "active",
        })
        customer_id = crm_create.get("customer_id", "cust_0008")

    # Step 1: CRM update_customer
    crm_update_req = {
        "customer_id": customer_id,
        "phone": new_phone,
        "address": new_address,
    }
    crm_update_res = crm_api.update_customer(crm_update_req)
    steps.append({
        "step_index": 1,
        "tool": "crm",
        "endpoint": "update_customer",
        "request": crm_update_req,
        "response": crm_update_res,
    })
    if crm_update_res.get("status") != "success":
        errors.extend(crm_update_res.get("errors", ["Customer update failed"]))
        return {
            "workflow_id": "W08",
            "workflow_name": "Update customer contact profile with new address, send confirmation email, and verify queued dispatch",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: Email send_email
    email_req = {
        "to": customer_email,
        "subject": "Profile Update Confirmation: Address and Contact Info Updated",
        "body": (
            f"Dear Customer ({customer_id}), your profile contact number has been updated to {new_phone} "
            f"and billing address has been relocated to {new_address.get('street')}, {new_address.get('city')}."
        ),
        "sender": {
            "email": "support@events.org",
            "name": "Customer Support Services",
        },
    }
    email_res = email_api.send_email(email_req)
    steps.append({
        "step_index": 2,
        "tool": "email",
        "endpoint": "send_email",
        "request": email_req,
        "response": email_res,
    })
    if email_res.get("status") != "success":
        errors.extend(email_res.get("errors", ["Email dispatch failed"]))
        return {
            "workflow_id": "W08",
            "workflow_name": "Update customer contact profile with new address, send confirmation email, and verify queued dispatch",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {"customer_id": customer_id},
            "errors": errors,
        }

    message_id = email_res["message_id"]

    # Step 3: Email get_email (verifies dispatch state using message_id)
    get_email_req = {
        "message_id": message_id,
    }
    get_email_res = email_api.get_email(get_email_req)
    steps.append({
        "step_index": 3,
        "tool": "email",
        "endpoint": "get_email",
        "request": get_email_req,
        "response": get_email_res,
    })
    if get_email_res.get("status") != "success":
        errors.extend(get_email_res.get("errors", ["Email verification failed"]))
        return {
            "workflow_id": "W08",
            "workflow_name": "Update customer contact profile with new address, send confirmation email, and verify queued dispatch",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {
                "customer_id": customer_id,
                "message_id": message_id,
            },
            "errors": errors,
        }

    return {
        "workflow_id": "W08",
        "workflow_name": "Update customer contact profile with new address, send confirmation email, and verify queued dispatch",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "message_id": message_id,
            "email_record": get_email_res.get("email", {}),
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_08()
    print("Workflow 08 Result:", result)
