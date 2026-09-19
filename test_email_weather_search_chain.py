"""Integration test chaining Search -> Weather -> Email mock tools.

Task workflow:
1. Search for outdoor event guidelines.
2. Fetch current weather and forecast for Mumbai.
3. Determine event recommendation (Go / No-Go) based on temperature and alerts.
4. Send notification email to the event attendee.

Also verifies error handling for deliberately invalid requests on each tool.
"""

from mock_tools.email_api import (
    _inspect_ground_truth as inspect_email_gt,
    send_email,
)
from mock_tools.search_api import (
    _inspect_ground_truth as inspect_search_gt,
    search,
)
from mock_tools.weather_api import (
    _inspect_ground_truth as inspect_weather_gt,
    get_current_weather,
    get_forecast,
)


def run_chain_test():
    print("==================================================")
    print("Starting Search -> Weather -> Email Chain Test")
    print("==================================================\n")

    # Step 1: Search for outdoor event guidelines
    print("[Step 1] Executing Search query for outdoor event guidelines...")
    search_response = search({"query": "outdoor event guidelines"})
    print("Search Response:", search_response)
    assert search_response["status"] == "success"
    assert search_response["total"] > 0
    top_doc = search_response["results"][0]
    print(f"Top guideline doc found: '{top_doc['title']}' (Score: {top_doc['score']})\n")

    # Step 2: Check current weather and forecast for Mumbai
    print("[Step 2] Fetching current weather and forecast for Mumbai...")
    weather_response = get_current_weather({"city": "Mumbai", "country_code": "IN"})
    print("Weather Current Response:", weather_response)
    assert weather_response["status"] == "success"

    temp = weather_response["temperature"]
    condition = weather_response["condition"]
    city = weather_response["city"]

    forecast_response = get_forecast({"city": "Mumbai", "days": 1})
    print("Weather Forecast Response:", forecast_response)
    assert forecast_response["status"] == "success"

    # Determine recommendation
    go_status = "GO" if temp < 35.0 and "Thunderstorm" not in condition else "NO-GO"
    email_body = (
        f"Event Status Update for {city}:\n"
        f"Based on current safety guidelines, the weather is {condition} with a temperature of {temp}°C.\n"
        f"Event Recommendation: {go_status}."
    )
    print(f"Computed decision: {go_status} (Temperature: {temp}°C)\n")

    # Step 3: Email attendee go/no-go note
    print("[Step 3] Sending notification email to attendee...")
    email_response = send_email(
        {
            "to": "attendee@example.com",
            "subject": f"Outdoor Event Status Notice - {go_status}",
            "body": email_body,
            "sender": {"email": "events@example.com", "name": "Event Ops Team"},
        }
    )
    print("Email Response:", email_response)
    assert email_response["status"] == "success"
    print("\n--- Valid Workflow Chain Completed Successfully ---\n")

    # Inspect ground truth states
    print("==================================================")
    print("Inspecting Ground Truth States")
    print("==================================================")
    email_gt = inspect_email_gt()
    weather_gt = inspect_weather_gt()
    search_gt = inspect_search_gt()

    print("\nEmail Ground Truth:")
    print(email_gt)

    print("\nWeather Ground Truth (Request Log Count):", len(weather_gt["request_log"]))
    print("Search Ground Truth (Request Log Count):", len(search_gt["request_log"]))

    # Assertions required by prompt
    # (a) outbox holds exactly one message
    assert len(email_gt["outbox"]) == 1, f"Expected outbox length 1, got {len(email_gt['outbox'])}"

    # (b) body contains the forecast temperature returned by Weather tool
    sent_msg_body = email_gt["outbox"][0]["body"]
    assert str(temp) in sent_msg_body, f"Expected temperature {temp} in email body, got: {sent_msg_body}"

    print("\n[PASS] Assertion passed: Outbox contains exactly 1 email.")
    print(f"[PASS] Assertion passed: Email body contains weather temperature ({temp} C).")

    # Step 4: Deliberately invalid requests per tool
    print("\n==================================================")
    print("Testing Deliberately Invalid Requests (Error Paths)")
    print("==================================================")

    # Email invalid: missing required 'to' field
    print("\n1. Testing Email API invalid request (missing required 'to' field)...")
    invalid_email_res = send_email({"subject": "No Recipient", "body": "Hello"})
    print("Invalid Email Response:", invalid_email_res)
    assert invalid_email_res["status"] == "error"
    assert "errors" in invalid_email_res
    print("[PASS] Email error path validated successfully.")

    # Weather invalid: missing required 'city' field
    print("\n2. Testing Weather API invalid request (missing required 'city' field)...")
    invalid_weather_res = get_current_weather({})
    print("Invalid Weather Response:", invalid_weather_res)
    assert invalid_weather_res["status"] == "error"
    assert "errors" in invalid_weather_res
    print("[PASS] Weather error path validated successfully.")

    # Search invalid: missing required 'query' field
    print("\n3. Testing Search API invalid request (missing required 'query' field)...")
    invalid_search_res = search({})
    print("Invalid Search Response:", invalid_search_res)
    assert invalid_search_res["status"] == "error"
    assert "errors" in invalid_search_res
    print("[PASS] Search error path validated successfully.")

    print("\n==================================================")
    print("All Chain and Validation Tests Passed Successfully!")
    print("==================================================")


if __name__ == "__main__":
    run_chain_test()
