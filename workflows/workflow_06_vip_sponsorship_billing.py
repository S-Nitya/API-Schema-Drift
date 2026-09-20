"""Workflow 06: VIP Sponsorship Registration and Billing.

API Sequence: Search (search) -> CRM (create_customer) -> Payment (charge_customer)
Stakes: High
Description: Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee.
"""

from typing import Any, Dict, Optional
import mock_tools.crm_api as crm_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api


def run_workflow_06(
    query: str = "VIP Ticketing Access Control guidelines",
    sponsor_name: str = "Global Nexus Ltd",
    sponsor_email: str = "vip@globalnexus.com",
    phone: str = "+91-9988776655",
    annual_revenue: float = 500000.0,
    vip_fee: float = 1200.0,
    currency: str = "USD",
    address: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Executes Workflow 06: Search -> CRM -> Payment."""
    if address is None:
        address = {
            "street": "42 Cyber Hub",
            "city": "Gurugram",
            "country": "IN",
            "postal_code": "122002",
        }

    steps = []
    errors = []

    # Step 1: Search for VIP ticketing guidelines
    search_req = {
        "query": query,
        "max_results": 2,
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
            "workflow_id": "W06",
            "workflow_name": "Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: CRM create_customer with revenue metadata
    crm_req = {
        "name": sponsor_name,
        "email": sponsor_email,
        "phone": phone,
        "company": "Global Nexus Ltd",
        "status": "active",
        "address": address,
        "metadata": {
            "tier": "VIP_PLATINUM",
            "annual_revenue": annual_revenue,
        },
    }
    crm_res = crm_api.create_customer(crm_req)
    steps.append({
        "step_index": 2,
        "tool": "crm",
        "endpoint": "create_customer",
        "request": crm_req,
        "response": crm_res,
    })
    if crm_res.get("status") != "success":
        errors.extend(crm_res.get("errors", ["CRM customer creation failed"]))
        return {
            "workflow_id": "W06",
            "workflow_name": "Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    customer_id = crm_res["customer_id"]

    # Step 3: Payment charge_customer
    pay_req = {
        "customer_id": customer_id,
        "amount": vip_fee,
        "currency": currency,
        "description": "VIP Platinum Event Pass Fee",
        "payment_method": "card",
    }
    pay_res = payment_api.charge_customer(pay_req)
    steps.append({
        "step_index": 3,
        "tool": "payment",
        "endpoint": "charge_customer",
        "request": pay_req,
        "response": pay_res,
    })
    if pay_res.get("status") != "success":
        errors.extend(pay_res.get("errors", ["Payment charge failed"]))
        return {
            "workflow_id": "W06",
            "workflow_name": "Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"customer_id": customer_id},
            "errors": errors,
        }

    transaction_id = pay_res["transaction_id"]

    return {
        "workflow_id": "W06",
        "workflow_name": "Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "customer_id": customer_id,
            "transaction_id": transaction_id,
            "amount_charged": vip_fee,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_06()
    print("Workflow 06 Result:", result)
