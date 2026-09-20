"""Workflow 07: Emergency Weather Bulletin Distribution.

API Sequence: Weather (get_alerts) -> Search (get_related_documents) -> Email (send_email)
Stakes: High
Description: Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin.
"""

from typing import Any, Dict, Optional
import mock_tools.email_api as email_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api


def run_workflow_07(
    city: str = "Bengaluru",
    document_id: str = "doc_011",  # Emergency Evacuation Plan
    broadcast_recipient: str = "all_attendees_bengaluru@events.org",
    cc_emails: Optional[list] = None,
    send_at: Optional[int] = 1700003600,
) -> Dict[str, Any]:
    """Executes Workflow 07: Weather -> Search -> Email."""
    if cc_emails is None:
        cc_emails = ["crisis.team@events.org", "venue.security@events.org"]

    steps = []
    errors = []

    # Step 1: Weather get_alerts
    alert_req = {
        "city": city,
    }
    alert_res = weather_api.get_alerts(alert_req)
    steps.append({
        "step_index": 1,
        "tool": "weather",
        "endpoint": "get_alerts",
        "request": alert_req,
        "response": alert_res,
    })
    if alert_res.get("status") != "success":
        errors.extend(alert_res.get("errors", ["Weather alert lookup failed"]))
        return {
            "workflow_id": "W07",
            "workflow_name": "Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    alerts = alert_res.get("alerts", [])
    alert_event = alerts[0].get("event", "Severe Weather Advisory") if alerts else "Severe Weather Advisory"

    # Step 2: Search get_related_documents for evacuation protocols
    doc_req = {
        "document_id": document_id,
        "max_results": 2,
    }
    doc_res = search_api.get_related_documents(doc_req)
    steps.append({
        "step_index": 2,
        "tool": "search",
        "endpoint": "get_related_documents",
        "request": doc_req,
        "response": doc_res,
    })
    if doc_res.get("status") != "success":
        errors.extend(doc_res.get("errors", ["Related documents retrieval failed"]))
        return {
            "workflow_id": "W07",
            "workflow_name": "Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"alerts": alert_res},
            "errors": errors,
        }

    # Step 3: Email send_email (high-priority emergency broadcast)
    email_req = {
        "to": broadcast_recipient,
        "subject": f"URGENT: Weather Action Bulletin for {city} - {alert_event}",
        "body": (
            f"URGENT NOTICE for {city} attendees: Active alert '{alert_event}' is in effect. "
            f"Per Emergency Protocol ({document_id}), all outdoor zones are being marshaled. "
            f"Please follow venue security instructions to designated shelter zones."
        ),
        "cc": cc_emails,
        "send_at": send_at,
        "sender": {
            "email": "emergency.command@events.org",
            "name": "Central Emergency Operations Command",
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
        errors.extend(email_res.get("errors", ["Emergency email broadcast failed"]))
        return {
            "workflow_id": "W07",
            "workflow_name": "Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin",
            "status": "error",
            "stakes": "high",
            "steps": steps,
            "outputs": {"city": city, "alert_event": alert_event},
            "errors": errors,
        }

    message_id = email_res["message_id"]

    return {
        "workflow_id": "W07",
        "workflow_name": "Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin",
        "status": "success",
        "stakes": "high",
        "steps": steps,
        "outputs": {
            "city": city,
            "alert_event": alert_event,
            "message_id": message_id,
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_07()
    print("Workflow 07 Result:", result)
