"""Workflow 09: Equipment Weather Guidelines and Operations Check.

API Sequence: Weather (get_current_weather) -> Search (get_document) -> Search (get_related_documents)
Stakes: Low
Description: Check Chennai current weather and retrieve equipment operational guidelines.
"""

from typing import Any, Dict
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api


def run_workflow_09(
    city: str = "Chennai",
    country_code: str = "IN",
    document_id: str = "doc_003",  # Venue Equipment Operations
) -> Dict[str, Any]:
    """Executes Workflow 09: Weather -> Search -> Search."""
    steps = []
    errors = []

    # Step 1: Weather get_current_weather
    weather_req = {
        "city": city,
        "country_code": country_code,
    }
    weather_res = weather_api.get_current_weather(weather_req)
    steps.append({
        "step_index": 1,
        "tool": "weather",
        "endpoint": "get_current_weather",
        "request": weather_req,
        "response": weather_res,
    })
    if weather_res.get("status") != "success":
        errors.extend(weather_res.get("errors", ["Weather lookup failed"]))
        return {
            "workflow_id": "W09",
            "workflow_name": "Check Chennai current weather and retrieve equipment operational guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    wind_speed = weather_res.get("wind_speed", 0.0)
    humidity = weather_res.get("humidity", 0)

    # Step 2: Search get_document for primary equipment guidelines
    doc_req = {
        "document_id": document_id,
    }
    doc_res = search_api.get_document(doc_req)
    steps.append({
        "step_index": 2,
        "tool": "search",
        "endpoint": "get_document",
        "request": doc_req,
        "response": doc_res,
    })
    if doc_res.get("status") != "success":
        errors.extend(doc_res.get("errors", ["Document retrieval failed"]))
        return {
            "workflow_id": "W09",
            "workflow_name": "Check Chennai current weather and retrieve equipment operational guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {"weather": weather_res},
            "errors": errors,
        }

    # Step 3: Search get_related_documents for companion contingency protocols
    rel_req = {
        "document_id": document_id,
        "max_results": 2,
    }
    rel_res = search_api.get_related_documents(rel_req)
    steps.append({
        "step_index": 3,
        "tool": "search",
        "endpoint": "get_related_documents",
        "request": rel_req,
        "response": rel_res,
    })
    if rel_res.get("status") != "success":
        errors.extend(rel_res.get("errors", ["Related documents lookup failed"]))
        return {
            "workflow_id": "W09",
            "workflow_name": "Check Chennai current weather and retrieve equipment operational guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {
                "weather": weather_res,
                "document": doc_res.get("document", {}),
            },
            "errors": errors,
        }

    return {
        "workflow_id": "W09",
        "workflow_name": "Check Chennai current weather and retrieve equipment operational guidelines",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "city": city,
            "wind_speed": wind_speed,
            "humidity": humidity,
            "primary_document": doc_res.get("document", {}),
            "related_count": rel_res.get("total", 0),
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_09()
    print("Workflow 09 Result:", result)
