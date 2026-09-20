"""Workflow 11: Venue Weather Assessment and Contingency Planning.

API Sequence: Weather (get_current_weather) -> Weather (get_forecast) -> Search (search)
Stakes: Low
Description: Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines.
"""

from typing import Any, Dict
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api


def run_workflow_11(
    city: str = "Pune",
    country_code: str = "IN",
    forecast_days: int = 2,
    search_query: str = "Weather Contingency Plan Template outdoor venues India",
) -> Dict[str, Any]:
    """Executes Workflow 11: Weather -> Weather -> Search."""
    steps = []
    errors = []

    # Step 1: Weather get_current_weather
    current_req = {
        "city": city,
        "country_code": country_code,
    }
    current_res = weather_api.get_current_weather(current_req)
    steps.append({
        "step_index": 1,
        "tool": "weather",
        "endpoint": "get_current_weather",
        "request": current_req,
        "response": current_res,
    })
    if current_res.get("status") != "success":
        errors.extend(current_res.get("errors", ["Current weather lookup failed"]))
        return {
            "workflow_id": "W11",
            "workflow_name": "Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {},
            "errors": errors,
        }

    # Step 2: Weather get_forecast
    forecast_req = {
        "city": city,
        "days": forecast_days,
    }
    forecast_res = weather_api.get_forecast(forecast_req)
    steps.append({
        "step_index": 2,
        "tool": "weather",
        "endpoint": "get_forecast",
        "request": forecast_req,
        "response": forecast_res,
    })
    if forecast_res.get("status") != "success":
        errors.extend(forecast_res.get("errors", ["Forecast retrieval failed"]))
        return {
            "workflow_id": "W11",
            "workflow_name": "Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {"current_weather": current_res},
            "errors": errors,
        }

    # Step 3: Search knowledge base for contingency guidelines
    search_req = {
        "query": search_query,
        "max_results": 2,
        "filters": {"category": "guidelines"},
    }
    search_res = search_api.search(search_req)
    steps.append({
        "step_index": 3,
        "tool": "search",
        "endpoint": "search",
        "request": search_req,
        "response": search_res,
    })
    if search_res.get("status") != "success":
        errors.extend(search_res.get("errors", ["Search lookup failed"]))
        return {
            "workflow_id": "W11",
            "workflow_name": "Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines",
            "status": "error",
            "stakes": "low",
            "steps": steps,
            "outputs": {
                "current_weather": current_res,
                "forecast": forecast_res,
            },
            "errors": errors,
        }

    return {
        "workflow_id": "W11",
        "workflow_name": "Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines",
        "status": "success",
        "stakes": "low",
        "steps": steps,
        "outputs": {
            "city": city,
            "current_temp": current_res.get("temperature", 0.0),
            "forecast_count": len(forecast_res.get("forecast", [])),
            "search_matches": search_res.get("total", 0),
        },
        "errors": [],
    }


if __name__ == "__main__":
    result = run_workflow_11()
    print("Workflow 11 Result:", result)
