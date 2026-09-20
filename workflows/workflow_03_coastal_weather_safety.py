"""Workflow 03: Coastal Weather Safety Advisory.

API Sequence: Search (search) -> Weather (get_current_weather) -> Email (send_email)
Stakes: Low
Description: Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers.
"""

from typing import Any, Dict, Optional
import mock_tools.email_api as email_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api


def run_workflow_03(
    query: str = "Mumbai Venue Operations Guide coastal weather",
    city: str = "Mumbai",
    country_code: str = "IN",
    organizer_email: str = "ops.lead@mumbaifest.org",
    cc_emails: Optional[list] = None,
) -> Dict[str, Any]:
    """Executes Workflow 03: Search -> Weather -> Email."""
    if cc_emails is None:
        cc_emails = ["safety.officer@mumbaifest.org"]

    steps = []
    errors = []

    # Step 1: Search for coastal venue operational guidelines
    search_req = {
        "query": query,
        "max_results": 2,
        "filters": {"category": "venue"},
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
            "workflow_id": "W03",
            "workflow_name": "Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: Weather get_current_weather
    weather_req = {
        "city": city,
        "country_code": country_code,
    }
    weather_res = weather_api.get_current_weather(weather_req)
    steps.append({
        "step_index": 2,
        "tool": "weather",
        "endpoint": "get_current_weather",
        "request": weather_req,
        "response": weather_res,
    })
    if weather_res.get("status") != "success":
        errors.extend(weather_res.get("errors", ["Weather lookup failed"]))
        return {
            "workflow_id": "W03",
            "workflow_name": "Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    temp = weather_res.get("temperature", 0.0)
    humidity = weather_res.get("humidity", 0)
    wind_speed = weather_res.get("wind_speed", 0.0)
    condition = weather_res.get("condition", "Unknown")

    # Step 3: Email send_email
    email_req = {
        "to": organizer_email,
        "subject": f"Weather Advisory: {city} Coastal Venue Status ({condition})",
        "body": (
            f"Dear Operations Team, Current live conditions in {city}: Temperature: {temp}°C, "
            f"Humidity: {humidity}%, Wind Speed: {wind_speed} m/s, Condition: {condition}. "
            f"Please adhere to coastal operations protocol and secure electrical setups."
        ),
        "cc": cc_emails,
        "sender": {
            "email": "weather.advisory@events.org",
            "name": "Meteorological Advisory Desk",
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
            "workflow_id": "W03",
            "workflow_name": "Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {"weather": weather_res},
            "errors": errors,
        }

    message_id = email_res["message_id"]

    return {
        "workflow_id": "W03",
        "workflow_name": "Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "city": city,
            "temperature": temp,
            "condition": condition,
            "message_id": message_id,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_03()
    print("Workflow 03 Result:", result)
