"""Workflow 04: Venue Forecast Reminder.

API Sequence: Weather (get_forecast) -> Email (send_email)
Stakes: Low
Description: Check 3-day forecast for Delhi outdoor venue and schedule automated logistical reminder.
"""

from typing import Any, Dict, Optional
import mock_tools.email_api as email_api
import mock_tools.weather_api as weather_api


def run_workflow_04(
    city: str = "Delhi",
    days: int = 3,
    venue_manager_email: str = "delhi.manager@events.org",
    send_at: Optional[int] = 1700014400,
) -> Dict[str, Any]:
    """Executes Workflow 04: Weather -> Email."""
    steps = []
    errors = []

    # Step 1: Weather get_forecast
    forecast_req = {
        "city": city,
        "days": days,
    }
    forecast_res = weather_api.get_forecast(forecast_req)
    steps.append({
        "step_index": 1,
        "tool": "weather",
        "endpoint": "get_forecast",
        "request": forecast_req,
        "response": forecast_res,
    })
    if forecast_res.get("status") != "success":
        errors.extend(forecast_res.get("errors", ["Forecast retrieval failed"]))
        return {
            "workflow_id": "W04",
            "workflow_name": "Check 3-day forecast for Delhi outdoor venue and schedule automated logistical reminder",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    forecast_list = forecast_res.get("forecast", [])
    day1_temp = forecast_list[0].get("temperature", 35.0) if forecast_list else 35.0
    day1_cond = forecast_list[0].get("condition", "Clear") if forecast_list else "Clear"

    # Step 2: Email send_email (scheduled send)
    email_req = {
        "to": venue_manager_email,
        "subject": f"Logistical Alert: 3-Day Weather Outlook for {city} Venue",
        "body": (
            f"Dear Venue Manager, the 3-day outlook for {city} predicts Day 1 at {day1_temp}°C ({day1_cond}). "
            f"Ensure shade covers and water hydration stations are positioned per high-heat protocols."
        ),
        "send_at": send_at,
        "sender": {
            "email": "logistics@events.org",
            "name": "Event Logistics Automated Bot",
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
            "workflow_id": "W04",
            "workflow_name": "Check 3-day forecast for Delhi outdoor venue and schedule automated logistical reminder",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {"forecast": forecast_res},
            "errors": errors,
        }

    message_id = email_res["message_id"]

    return {
        "workflow_id": "W04",
        "workflow_name": "Check 3-day forecast for Delhi outdoor venue and schedule automated logistical reminder",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "city": city,
            "forecast_days": len(forecast_list),
            "day1_temperature": day1_temp,
            "message_id": message_id,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_04()
    print("Workflow 04 Result:", result)
