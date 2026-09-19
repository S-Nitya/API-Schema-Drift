"""Integration test chaining all 5 mock tools: Search -> CRM -> Payment -> Weather -> Email.

Workflow Scenario:
1. Search: Search knowledge base for VIP event ticketing rules and pass pricing policy.
2. CRM: Create customer record for VIP member signup (e.g., 'Ananya Verma').
3. Payment: Charge member the VIP ticket fee ($99.00 USD) and capture transaction ID.
4. CRM: Update customer profile with premium active status and transaction cross-reference.
5. Weather: Check live weather conditions for the venue city (e.g., Bengaluru).
6. Email: Dispatch a personalized confirmation email containing customer ID, payment reference, and local weather.
7. Verification: Inspect ground truth across all 5 tools to confirm end-to-end state consistency.
8. Error Path Testing: Confirm validation errors and failure paths across all tools.
"""

from mock_tools import (
    charge_customer,
    create_customer,
    get_current_weather,
    get_customer,
    get_document,
    get_transaction,
    inspect_crm_ground_truth,
    inspect_email_ground_truth,
    inspect_payment_ground_truth,
    inspect_search_ground_truth,
    inspect_weather_ground_truth,
    reset_crm_ground_truth,
    reset_email_ground_truth,
    reset_payment_ground_truth,
    reset_search_ground_truth,
    reset_weather_ground_truth,
    search,
    send_email,
    update_customer,
)


def run_full_integration_test():
    print("=================================================================")
    print("Starting Unified 5-Tool Integration Test")
    print("Search -> CRM -> Payment -> Weather -> Email")
    print("=================================================================\n")

    # Reset all ground truth states for a clean, deterministic run
    reset_crm_ground_truth()
    reset_payment_ground_truth()
    reset_email_ground_truth()
    reset_weather_ground_truth()
    reset_search_ground_truth()

    # -------------------------------------------------------------
    # Step 1: Search for VIP ticketing policies
    # -------------------------------------------------------------
    print("[Step 1] Querying knowledge base for VIP ticketing policies...")
    search_res = search({"query": "VIP Ticketing Access Control"})
    print("Search Response:", search_res)
    assert search_res["status"] == "success", f"Search failed: {search_res}"
    assert search_res["total"] > 0, "No search results returned"
    vip_doc = search_res["results"][0]
    print(f"Top matching policy: '{vip_doc['title']}' (ID: {vip_doc['id']})\n")

    # Retrieve full document
    doc_res = get_document({"document_id": vip_doc["id"]})
    print("Document Details:", doc_res)
    assert doc_res["status"] == "success"

    # -------------------------------------------------------------
    # Step 2: Create customer record in CRM
    # -------------------------------------------------------------
    print("[Step 2] Creating customer profile in CRM...")
    cust_payload = {
        "name": "Ananya Verma",
        "email": "ananya.verma@example.com",
        "phone": "+91-9812345678",
        "company": "Tech Innovations Ltd",
        "status": "prospect",
        "address": {
            "street": "45 Residency Road",
            "city": "Bengaluru",
            "country": "India",
            "postal_code": "560025",
        },
        "metadata": {"source": "vip_registration_portal"},
    }
    crm_res = create_customer(cust_payload)
    print("CRM Create Customer Response:", crm_res)
    assert crm_res["status"] == "success", f"Customer creation failed: {crm_res}"
    customer_id = crm_res["customer_id"]
    print(f"Customer registered with ID: '{customer_id}'\n")

    # -------------------------------------------------------------
    # Step 3: Charge VIP membership / ticket fee via Payment API
    # -------------------------------------------------------------
    ticket_amount = 99.00
    currency = "USD"
    print(f"[Step 3] Charging customer {customer_id} ${ticket_amount} {currency} for VIP Access...")
    charge_payload = {
        "customer_id": customer_id,
        "amount": ticket_amount,
        "currency": currency,
        "description": "VIP Pass & Annual Access",
        "payment_method": "card",
        "metadata": {"ticket_type": "VIP", "policy_ref": vip_doc["id"]},
    }
    payment_res = charge_customer(charge_payload)
    print("Payment Charge Response:", payment_res)
    assert payment_res["status"] == "success", f"Payment failed: {payment_res}"
    transaction_id = payment_res["transaction_id"]
    assert payment_res["amount"] == ticket_amount
    print(f"Payment charged successfully. Transaction ID: '{transaction_id}'\n")

    # -------------------------------------------------------------
    # Step 4: Update CRM customer status with transaction info
    # -------------------------------------------------------------
    print("[Step 4] Updating CRM customer status to 'active_vip'...")
    update_crm_res = update_customer(
        {
            "customer_id": customer_id,
            "status": "active_vip",
            "metadata": {
                "source": "vip_registration_portal",
                "vip_transaction_id": transaction_id,
                "membership_fee_paid": str(ticket_amount),
            },
        }
    )
    print("CRM Update Response:", update_crm_res)
    assert update_crm_res["status"] == "success"

    # Verify CRM updated record
    cust_record = get_customer({"customer_id": customer_id})
    assert cust_record["status"] == "success"
    assert cust_record["customer"]["status"] == "active_vip"
    print(f"Customer record verified for '{customer_id}'.\n")

    # -------------------------------------------------------------
    # Step 5: Check live weather conditions for the venue city
    # -------------------------------------------------------------
    city_name = "Bengaluru"
    print(f"[Step 5] Checking weather conditions for event city '{city_name}'...")
    weather_res = get_current_weather({"city": city_name, "country_code": "IN"})
    print("Weather Response:", weather_res)
    assert weather_res["status"] == "success", f"Weather lookup failed: {weather_res}"
    temp = weather_res["temperature"]
    condition = weather_res["condition"]
    print(f"Weather in {city_name}: {condition}, {temp}°C\n")

    # -------------------------------------------------------------
    # Step 6: Dispatch customized confirmation email via Email API
    # -------------------------------------------------------------
    email_subject = "Your VIP Access Confirmation & Venue Guide"
    email_body = (
        f"Dear Ananya Verma,\n\n"
        f"Thank you for signing up for VIP Access! Your registration is confirmed.\n"
        f"Customer ID: {customer_id}\n"
        f"Transaction Reference: {transaction_id} (Amount: ${ticket_amount} {currency})\n\n"
        f"Event Venue: {city_name}\n"
        f"Current Local Weather: {condition} at {temp}°C.\n\n"
        f"We look forward to seeing you at the event!\n"
        f"Best regards,\nEvent Ops & Hospitality Team"
    )

    print("[Step 6] Sending VIP confirmation email...")
    email_res = send_email(
        {
            "to": "ananya.verma@example.com",
            "subject": email_subject,
            "body": email_body,
            "sender": {"email": "vip-desk@eventops.org", "name": "VIP Concierge"},
        }
    )
    print("Email Response:", email_res)
    assert email_res["status"] == "success", f"Email dispatch failed: {email_res}"
    message_id = email_res["message_id"]
    print(f"Confirmation email queued with Message ID: '{message_id}'\n")

    # -------------------------------------------------------------
    # Step 7: Inspect and Assert Ground Truth Across All 5 Tools
    # -------------------------------------------------------------
    print("=================================================================")
    print("Inspecting Ground Truth Across All 5 Tools")
    print("=================================================================")

    crm_gt = inspect_crm_ground_truth()
    payment_gt = inspect_payment_ground_truth()
    email_gt = inspect_email_ground_truth()
    weather_gt = inspect_weather_ground_truth()
    search_gt = inspect_search_ground_truth()

    # 1. CRM Ground Truth Assertions
    assert customer_id in crm_gt["customers"]
    assert crm_gt["customers"][customer_id]["name"] == "Ananya Verma"
    assert crm_gt["customers"][customer_id]["status"] == "active_vip"
    print(f"[PASS] CRM ground truth verified for customer {customer_id}.")

    # 2. Payment Ground Truth Assertions
    assert transaction_id in payment_gt["transactions"]
    assert payment_gt["transactions"][transaction_id]["customer_id"] == customer_id
    assert payment_gt["transactions"][transaction_id]["amount"] == ticket_amount
    assert payment_gt["transactions"][transaction_id]["transaction_status"] == "succeeded"
    print(f"[PASS] Payment ground truth verified for transaction {transaction_id}.")

    # 3. Email Ground Truth Assertions
    assert len(email_gt["outbox"]) == 1
    sent_email = email_gt["outbox"][0]
    assert sent_email["message_id"] == message_id
    assert sent_email["to"] == "ananya.verma@example.com"
    assert customer_id in sent_email["body"]
    assert transaction_id in sent_email["body"]
    assert str(temp) in sent_email["body"]
    print(f"[PASS] Email ground truth verified with correct cross-references.")

    # 4. Weather & Search Ground Truth Request Logs
    assert len(weather_gt["request_log"]) >= 1
    assert len(search_gt["request_log"]) >= 2
    print(f"[PASS] Weather request log count: {len(weather_gt['request_log'])}")
    print(f"[PASS] Search request log count: {len(search_gt['request_log'])}")

    # -------------------------------------------------------------
    # Step 8: Error Path & Schema Validation Across Tools
    # -------------------------------------------------------------
    print("\n=================================================================")
    print("Testing Error Paths and Validation Across Tools")
    print("=================================================================")

    # CRM invalid
    err_crm = create_customer({"name": "No Email User"})
    assert err_crm["status"] == "error"
    print("[PASS] CRM rejected missing required field.")

    # Payment invalid
    err_pay = charge_customer({"customer_id": customer_id, "amount": -10.0})
    assert err_pay["status"] == "error"
    print("[PASS] Payment rejected invalid non-positive amount.")

    # Email invalid
    err_mail = send_email({"subject": "No recipient", "body": "Test"})
    assert err_mail["status"] == "error"
    print("[PASS] Email rejected missing 'to' recipient.")

    # Weather invalid
    err_weather = get_current_weather({"city": "UnknownCityXYZ"})
    assert err_weather["status"] == "error"
    print("[PASS] Weather rejected non-existent city.")

    # Search invalid
    err_search = search({})
    assert err_search["status"] == "error"
    print("[PASS] Search rejected missing query parameter.")

    print("\n=================================================================")
    print("All 5 Tools Successfully Integrated and Verified!")
    print("=================================================================")


if __name__ == "__main__":
    run_full_integration_test()
