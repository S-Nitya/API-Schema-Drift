"""Mock Weather API tool following OpenWeatherMap conventions.

Units convention:
- temperature: float in degrees Celsius (°C)
- wind_speed: float in meters per second (m/s)
- humidity: int in percentage (%)

Field names intentionally do not include unit suffixes (e.g. 'temperature', not 'temperature_c')
so semantic drift (e.g. Celsius -> Fahrenheit) can be tested later.
"""

import copy

# 1. SCHEMA: Module-level contract definition.
SCHEMA = {
    "tool": "weather",
    "endpoints": {
        "get_current_weather": {
            "request": {
                "city": {
                    "type": str,
                    "required": True,
                    "description": "City name for weather lookup",
                },
                "country_code": {
                    "type": str,
                    "required": False,
                    "description": "Two-letter ISO country code (e.g., IN, US)",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call ('success' or 'error')"},
                "city": {"type": str, "required": True, "description": "City name"},
                "temperature": {"type": float, "required": True, "description": "Temperature in degrees Celsius"},
                "humidity": {"type": int, "required": True, "description": "Humidity percentage (0-100)"},
                "wind_speed": {"type": float, "required": True, "description": "Wind speed in meters per second"},
                "condition": {"type": str, "required": True, "description": "Weather condition summary"},
            },
        },
        "get_forecast": {
            "request": {
                "city": {
                    "type": str,
                    "required": True,
                    "description": "City name for weather forecast lookup",
                },
                "days": {
                    "type": int,
                    "required": False,
                    "description": "Number of forecast days to return (1-3)",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "city": {"type": str, "required": True, "description": "City name"},
                "forecast": {"type": list, "required": True, "description": "List of daily weather forecast entries"},
            },
        },
        "get_alerts": {
            "request": {
                "city": {
                    "type": str,
                    "required": True,
                    "description": "City name for weather alert lookup",
                },
            },
            "response": {
                "status": {"type": str, "required": True, "description": "Status of the API call"},
                "city": {"type": str, "required": True, "description": "City name"},
                "alerts": {"type": list, "required": True, "description": "List of active weather alert warnings"},
            },
        },
    },
}

# 2. Ground truth state: Read-only fixture dataset and private request log.
_WEATHER_DATA = {
    "mumbai": {
        "city": "Mumbai",
        "country_code": "IN",
        "current": {
            "temperature": 28.5,  # degrees Celsius
            "humidity": 78,       # %
            "wind_speed": 4.5,    # m/s
            "condition": "Light Rain",
        },
        "forecast": [
            {"day": 1, "temperature": 29.0, "humidity": 75, "wind_speed": 4.2, "condition": "Partly Cloudy"},
            {"day": 2, "temperature": 28.0, "humidity": 80, "wind_speed": 5.1, "condition": "Moderate Rain"},
            {"day": 3, "temperature": 27.5, "humidity": 82, "wind_speed": 5.5, "condition": "Thunderstorm"},
        ],
        "alerts": [
            {
                "event": "Heavy Rain Warning",
                "severity": "Moderate",
                "description": "Expect intermittent heavy rainfall over coastal areas.",
            }
        ],
    },
    "delhi": {
        "city": "Delhi",
        "country_code": "IN",
        "current": {
            "temperature": 34.0,
            "humidity": 45,
            "wind_speed": 3.0,
            "condition": "Hazy Sunshine",
        },
        "forecast": [
            {"day": 1, "temperature": 35.0, "humidity": 42, "wind_speed": 3.2, "condition": "Clear"},
            {"day": 2, "temperature": 36.0, "humidity": 40, "wind_speed": 2.8, "condition": "Hot"},
            {"day": 3, "temperature": 34.5, "humidity": 48, "wind_speed": 3.5, "condition": "Partly Cloudy"},
        ],
        "alerts": [],
    },
    "bengaluru": {
        "city": "Bengaluru",
        "country_code": "IN",
        "current": {
            "temperature": 24.0,
            "humidity": 65,
            "wind_speed": 5.0,
            "condition": "Pleasant",
        },
        "forecast": [
            {"day": 1, "temperature": 25.0, "humidity": 62, "wind_speed": 4.8, "condition": "Partly Cloudy"},
            {"day": 2, "temperature": 24.5, "humidity": 68, "wind_speed": 5.2, "condition": "Light Showers"},
            {"day": 3, "temperature": 23.8, "humidity": 70, "wind_speed": 4.5, "condition": "Cloudy"},
        ],
        "alerts": [],
    },
    "pune": {
        "city": "Pune",
        "country_code": "IN",
        "current": {
            "temperature": 26.5,
            "humidity": 60,
            "wind_speed": 3.8,
            "condition": "Overcast",
        },
        "forecast": [
            {"day": 1, "temperature": 27.0, "humidity": 58, "wind_speed": 4.0, "condition": "Passing Clouds"},
            {"day": 2, "temperature": 26.0, "humidity": 63, "wind_speed": 3.6, "condition": "Drizzle"},
            {"day": 3, "temperature": 25.5, "humidity": 65, "wind_speed": 4.1, "condition": "Light Rain"},
        ],
        "alerts": [],
    },
    "chennai": {
        "city": "Chennai",
        "country_code": "IN",
        "current": {
            "temperature": 31.0,
            "humidity": 72,
            "wind_speed": 6.0,
            "condition": "Humid",
        },
        "forecast": [
            {"day": 1, "temperature": 31.5, "humidity": 70, "wind_speed": 5.8, "condition": "Sunny"},
            {"day": 2, "temperature": 32.0, "humidity": 68, "wind_speed": 6.2, "condition": "Clear"},
            {"day": 3, "temperature": 30.5, "humidity": 75, "wind_speed": 6.5, "condition": "Scattered Clouds"},
        ],
        "alerts": [],
    },
}

_GROUND_TRUTH = {
    "weather_data": _WEATHER_DATA,
    "request_log": [],
}


# 3. _validate: Schema validation engine reading SCHEMA at call time.
def _validate(endpoint: str, request: dict) -> list[str]:
    """Validates a request dictionary against the live SCHEMA definition."""
    errors = []
    if not isinstance(request, dict):
        return ["Request must be a dictionary"]

    endpoints = SCHEMA.get("endpoints", {})
    if endpoint not in endpoints:
        return [f"Unknown endpoint: '{endpoint}'"]

    req_schema = endpoints[endpoint].get("request", {})
    for field_name, field_def in req_schema.items():
        expected_type = field_def.get("type")
        is_required = field_def.get("required", False)

        if field_name not in request or request[field_name] is None:
            if is_required:
                errors.append(f"Missing required field: '{field_name}'")
            continue

        val = request[field_name]

        if expected_type is int:
            if isinstance(val, bool) or not isinstance(val, int):
                errors.append(f"Field '{field_name}' must be of type int, got {type(val).__name__}")
        elif expected_type is float:
            if isinstance(val, bool) or not isinstance(val, (float, int)):
                errors.append(f"Field '{field_name}' must be of type float, got {type(val).__name__}")
        elif expected_type is str:
            if not isinstance(val, str):
                errors.append(f"Field '{field_name}' must be of type str, got {type(val).__name__}")
        elif expected_type is list:
            if not isinstance(val, list):
                errors.append(f"Field '{field_name}' must be of type list, got {type(val).__name__}")
        elif expected_type is dict:
            if not isinstance(val, dict):
                errors.append(f"Field '{field_name}' must be of type dict, got {type(val).__name__}")

    return errors


def _extract_recognized_fields(endpoint: str, request: dict) -> dict:
    """Extracts only fields recognized by the current SCHEMA endpoint definition."""
    req_schema = SCHEMA.get("endpoints", {}).get(endpoint, {}).get("request", {})
    extracted = {}
    for field_name in req_schema:
        if field_name in request and request[field_name] is not None:
            extracted[field_name] = request[field_name]
    return extracted


def _log_request(endpoint: str, request: dict, response: dict) -> None:
    """Logs request and response to private ground truth log."""
    _GROUND_TRUTH["request_log"].append(
        {
            "endpoint": endpoint,
            "request": copy.deepcopy(request),
            "response": copy.deepcopy(response),
        }
    )


# 4. Handler functions: Validate request, read ground truth, return response.
def get_current_weather(request: dict = None, **kwargs) -> dict:
    """Gets current weather conditions for a specified city."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_current_weather", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("get_current_weather", request, res)
        return res

    payload = _extract_recognized_fields("get_current_weather", request)
    city_raw = payload["city"]
    city_key = city_raw.strip().lower()

    if city_key not in _WEATHER_DATA:
        res = {"status": "error", "errors": [f"City '{city_raw}' not found in weather database"]}
        _log_request("get_current_weather", request, res)
        return res

    city_info = _WEATHER_DATA[city_key]
    current = city_info["current"]

    res = {
        "status": "success",
        "city": city_info["city"],
        "temperature": float(current["temperature"]),
        "humidity": int(current["humidity"]),
        "wind_speed": float(current["wind_speed"]),
        "condition": str(current["condition"]),
    }
    _log_request("get_current_weather", request, res)
    return res


def get_forecast(request: dict = None, **kwargs) -> dict:
    """Gets daily weather forecast for a specified city."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_forecast", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("get_forecast", request, res)
        return res

    payload = _extract_recognized_fields("get_forecast", request)
    city_raw = payload["city"]
    city_key = city_raw.strip().lower()

    if city_key not in _WEATHER_DATA:
        res = {"status": "error", "errors": [f"City '{city_raw}' not found in weather database"]}
        _log_request("get_forecast", request, res)
        return res

    city_info = _WEATHER_DATA[city_key]
    forecast_list = copy.deepcopy(city_info["forecast"])

    days = payload.get("days")
    if days is not None and days > 0:
        forecast_list = forecast_list[:days]

    res = {
        "status": "success",
        "city": city_info["city"],
        "forecast": forecast_list,
    }
    _log_request("get_forecast", request, res)
    return res


def get_alerts(request: dict = None, **kwargs) -> dict:
    """Gets active weather alerts for a specified city."""
    if request is None:
        request = kwargs
    elif kwargs:
        request = {**request, **kwargs}

    errors = _validate("get_alerts", request)
    if errors:
        res = {"status": "error", "errors": errors}
        _log_request("get_alerts", request, res)
        return res

    payload = _extract_recognized_fields("get_alerts", request)
    city_raw = payload["city"]
    city_key = city_raw.strip().lower()

    if city_key not in _WEATHER_DATA:
        res = {"status": "error", "errors": [f"City '{city_raw}' not found in weather database"]}
        _log_request("get_alerts", request, res)
        return res

    city_info = _WEATHER_DATA[city_key]
    alerts_list = copy.deepcopy(city_info["alerts"])

    res = {
        "status": "success",
        "city": city_info["city"],
        "alerts": alerts_list,
    }
    _log_request("get_alerts", request, res)
    return res


# 5. _inspect_ground_truth: Test-only helper returning direct copy of ground truth.
def _inspect_ground_truth() -> dict:
    """Returns a deep copy of the private ground truth state for testing."""
    return copy.deepcopy(_GROUND_TRUTH)


def _reset_ground_truth() -> None:
    """Resets the ground truth request log (test helper)."""
    _GROUND_TRUTH["request_log"] = []


# 6. Smoke test execution block.
if __name__ == "__main__":
    print("=== Weather API Smoke Test ===")
    cur_res = get_current_weather({"city": "Mumbai", "country_code": "IN"})
    print("Current Weather:", cur_res)

    fc_res = get_forecast({"city": "Mumbai", "days": 2})
    print("Forecast:", fc_res)

    alerts_res = get_alerts({"city": "Mumbai"})
    print("Alerts:", alerts_res)

    print("Ground Truth Log Count:", len(_inspect_ground_truth()["request_log"]))
