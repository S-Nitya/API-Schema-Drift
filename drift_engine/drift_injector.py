"""Drift Injection Engine core module.

Provides the DriftInjector class, 30-cell catalog, dynamic schema patching,
handler wrapping, request/response translation, stacking, and deterministic logging.
"""

import copy
import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import mock_tools.crm_api as crm_api
import mock_tools.email_api as email_api
import mock_tools.payment_api as payment_api
import mock_tools.search_api as search_api
import mock_tools.weather_api as weather_api


class MidTaskInjectionError(Exception):
    """Raised when inject() is called during an active task without allow_mid_task=True."""
    pass


class ConflictingDriftError(Exception):
    """Raised when attempting to inject a drift on a tool/endpoint/field combination already affected."""
    pass


class InvalidDriftError(Exception):
    """Raised when an unrecognized drift_id or catalog configuration is requested."""
    pass


class UnknownToolError(Exception):
    """Raised when an unrecognized tool name is provided."""
    pass


# Map tool names to modules
_TOOL_MODULES = {
    "crm": crm_api,
    "payment": payment_api,
    "weather": weather_api,
    "search": search_api,
    "email": email_api,
}


def _epoch_to_iso(epoch_val: Any) -> Any:
    """Converts epoch int/float timestamp to ISO-8601 UTC string."""
    if isinstance(epoch_val, (int, float)) and not isinstance(epoch_val, bool):
        dt = datetime.datetime.fromtimestamp(epoch_val, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return epoch_val


# Catalog definition for all 30 cells (6 drift types x 5 tools)
# Key: (drift_id, tool_name)
DRIFT_CATALOG: Dict[Tuple[str, str], Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # CRM API
    # -------------------------------------------------------------------------
    ("D1", "crm"): {
        "drift_name": "Request Field Rename",
        "endpoints": ["create_customer", "update_customer"],
        "fields": ["phone"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A"],
        "description": "Renames optional request field 'phone' to 'Phone_Number' in CRM create and update endpoints.",
        "apply_schema": lambda schema: _rename_req_field(schema, ["create_customer", "update_customer"], "phone", "Phone_Number"),
        "request_transform": lambda ep, req: _rename_dict_key(req, "Phone_Number", "phone"),
        "response_transform": lambda ep, res: res,
    },
    ("D2", "crm"): {
        "drift_name": "Response Format Change",
        "endpoints": ["create_customer", "update_customer", "get_customer", "list_customers"],
        "fields": ["created_at", "updated_at"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B"],
        "description": "Converts unix epoch timestamps 'created_at' and 'updated_at' to ISO-8601 strings in CRM responses.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _crm_d2_response(ep, res),
    },
    ("D3", "crm"): {
        "drift_name": "Value Meaning Change",
        "endpoints": ["create_customer", "update_customer", "get_customer", "list_customers"],
        "fields": ["annual_revenue"],  # NOTE: CRM has no top-level annual_revenue field; transformed when present in metadata or customer payload
        "schema_visible": False,
        "expected_detectors": ["Strategy C"],
        "description": "Transforms revenue values in metadata or customer payload by dividing by 1000 (thousands unit shift).",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _crm_d3_response(ep, res),
    },
    ("D4", "crm"): {
        "drift_name": "Nested <-> Flat Structure",
        "endpoints": ["create_customer", "update_customer", "get_customer", "list_customers"],
        "fields": ["address"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy B"],
        "description": "Flattens nested 'address' dict into separate 'address_street', 'address_city', 'address_country', 'address_postal_code' fields.",
        "apply_schema": lambda schema: _crm_d4_schema(schema),
        "request_transform": lambda ep, req: _crm_d4_req_transform(req),
        "response_transform": lambda ep, res: _crm_d4_res_transform(ep, res),
    },
    ("D5", "crm"): {
        "drift_name": "Silent Null Response",
        "endpoints": ["get_customer", "list_customers"],
        "fields": ["email"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B", "Strategy C"],
        "description": "Sets returned customer email field to None silently.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _crm_d5_response(ep, res),
    },
    ("D6", "crm"): {
        "drift_name": "Endpoint Deprecation with Fallback",
        "endpoints": ["get_customer"],
        "fields": ["get_customer"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy C"],
        "description": "Marks 'get_customer' deprecated in favor of 'get_customer_v2'; old endpoint returns static placeholder record without reading ground truth.",
        "apply_schema": lambda schema: _deprecate_endpoint(schema, "get_customer"),
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: res,
        "fallback_response": lambda ep, req: {
            "status": "success",
            "customer": {
                "customer_id": req.get("customer_id", "cust_0000"),
                "name": "Placeholder Customer",
                "email": "placeholder@example.com",
                "phone": "+0-0000000000",
                "company": "Placeholder Inc",
                "status": "active",
                "created_at": 1700000000,
                "updated_at": 1700000000,
            },
        },
    },

    # -------------------------------------------------------------------------
    # Payment API
    # -------------------------------------------------------------------------
    ("D1", "payment"): {
        "drift_name": "Request Field Rename",
        "endpoints": ["charge_customer"],
        "fields": ["description"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A"],
        "description": "Renames optional request field 'description' to 'statement_descriptor' in charge_customer.",
        "apply_schema": lambda schema: _rename_req_field(schema, ["charge_customer"], "description", "statement_descriptor"),
        "request_transform": lambda ep, req: _rename_dict_key(req, "statement_descriptor", "description"),
        "response_transform": lambda ep, res: res,
    },
    ("D2", "payment"): {
        "drift_name": "Response Format Change",
        "endpoints": ["charge_customer", "refund_customer", "get_transaction", "list_transactions"],
        "fields": ["amount", "amount_refunded"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B"],
        "description": "Converts float amounts (e.g. 50.0) to 2-decimal formatted string representations (e.g. '50.00').",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _payment_d2_response(ep, res),
    },
    ("D3", "payment"): {
        "drift_name": "Value Meaning Change",
        "endpoints": ["charge_customer", "refund_customer", "get_transaction", "list_transactions"],
        "fields": ["amount", "amount_refunded"],
        "schema_visible": False,
        "expected_detectors": ["Strategy C"],
        "description": "Converts returned payment amounts from major currency units (dollars) to minor units (cents, x100).",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _payment_d3_response(ep, res),
    },
    ("D4", "payment"): {
        "drift_name": "Nested <-> Flat Structure",
        "endpoints": ["charge_customer"],
        "fields": ["payment_method"],  # NOTE: Built tool used flat string; reverse direction (nesting flat field) applied
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy B"],
        "description": "Converts flat string 'payment_method' field into a nested object schema payment_method: {type, details}.",
        "apply_schema": lambda schema: _payment_d4_schema(schema),
        "request_transform": lambda ep, req: _payment_d4_req_transform(req),
        "response_transform": lambda ep, res: res,
    },
    ("D5", "payment"): {
        "drift_name": "Silent Null Response",
        "endpoints": ["charge_customer", "refund_customer", "get_transaction", "list_transactions"],
        "fields": ["transaction_id"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B", "Strategy C"],
        "description": "Sets transaction_id to None in responses silently.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _payment_d5_response(ep, res),
    },
    ("D6", "payment"): {
        "drift_name": "Endpoint Deprecation with Fallback",
        "endpoints": ["refund_customer"],
        "fields": ["refund_customer"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy C"],
        "description": "Marks 'refund_customer' deprecated in favor of 'refund_customer_v2'; old returns success with amount_refunded=0.0 without mutating ground truth.",
        "apply_schema": lambda schema: _deprecate_endpoint(schema, "refund_customer"),
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: res,
        "fallback_response": lambda ep, req: {
            "status": "success",
            "refund_id": "ref_0000",
            "transaction_id": req.get("transaction_id", "tx_0000"),
            "amount_refunded": 0.0,
            "currency": "USD",
            "created_at": 1700000000,
        },
    },

    # -------------------------------------------------------------------------
    # Weather API
    # -------------------------------------------------------------------------
    ("D1", "weather"): {
        "drift_name": "Request Field Rename",
        "endpoints": ["get_current_weather"],
        "fields": ["country_code"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A"],
        "description": "Renames optional request field 'country_code' to 'country' in get_current_weather.",
        "apply_schema": lambda schema: _rename_req_field(schema, ["get_current_weather"], "country_code", "country"),
        "request_transform": lambda ep, req: _rename_dict_key(req, "country", "country_code"),
        "response_transform": lambda ep, res: res,
    },
    ("D2", "weather"): {
        "drift_name": "Response Format Change",
        "endpoints": ["get_current_weather", "get_forecast"],
        "fields": ["humidity"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B"],
        "description": "Formats int humidity value (e.g. 62) as a percentage string (e.g. '62%').",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _weather_d2_response(ep, res),
    },
    ("D3", "weather"): {
        "drift_name": "Value Meaning Change",
        "endpoints": ["get_current_weather", "get_forecast"],
        "fields": ["wind_speed"],
        "schema_visible": False,
        "expected_detectors": ["Strategy C"],
        "description": "Converts wind_speed units from meters/second (m/s) to kilometers/hour (km/h, x3.6).",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _weather_d3_response(ep, res),
    },
    ("D4", "weather"): {
        "drift_name": "Nested <-> Flat Structure",
        "endpoints": ["get_current_weather"],
        "fields": ["location"],  # NOTE: Built tool used flat fields city & country_code; reverse direction (nesting flat fields) applied
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy B"],
        "description": "Nests flat 'city' and 'country_code' fields into a 'location' object request parameter.",
        "apply_schema": lambda schema: _weather_d4_schema(schema),
        "request_transform": lambda ep, req: _weather_d4_req_transform(req),
        "response_transform": lambda ep, res: res,
    },
    ("D5", "weather"): {
        "drift_name": "Silent Null Response",
        "endpoints": ["get_current_weather", "get_forecast"],
        "fields": ["temperature"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B", "Strategy C"],
        "description": "Sets returned temperature value to None silently.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _weather_d5_response(ep, res),
    },
    ("D6", "weather"): {
        "drift_name": "Endpoint Deprecation with Fallback",
        "endpoints": ["get_forecast"],
        "fields": ["get_forecast"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy C"],
        "description": "Marks 'get_forecast' deprecated in favor of 'get_forecast_v2'; old endpoint returns forecast for Delhi regardless of requested city.",
        "apply_schema": lambda schema: _deprecate_endpoint(schema, "get_forecast"),
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: res,
        "fallback_response": lambda ep, req: {
            "status": "success",
            "city": "Delhi",
            "forecast": [
                {"day": 1, "temperature": 35.0, "humidity": 42, "wind_speed": 3.2, "condition": "Clear"},
                {"day": 2, "temperature": 36.0, "humidity": 40, "wind_speed": 2.8, "condition": "Hot"},
            ],
        },
    },

    # -------------------------------------------------------------------------
    # Search API
    # -------------------------------------------------------------------------
    ("D1", "search"): {
        "drift_name": "Request Field Rename",
        "endpoints": ["search", "get_related_documents"],
        "fields": ["max_results"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A"],
        "description": "Renames optional request field 'max_results' to 'limit' in search and get_related_documents.",
        "apply_schema": lambda schema: _rename_req_field(schema, ["search", "get_related_documents"], "max_results", "limit"),
        "request_transform": lambda ep, req: _rename_dict_key(req, "limit", "max_results"),
        "response_transform": lambda ep, res: res,
    },
    ("D2", "search"): {
        "drift_name": "Response Format Change",
        "endpoints": ["search", "get_related_documents"],
        "fields": ["score"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B"],
        "description": "Converts float relevance scores to string representations (e.g. 0.85 -> '0.85').",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _search_d2_response(ep, res),
    },
    ("D3", "search"): {
        "drift_name": "Value Meaning Change",
        "endpoints": ["search", "get_related_documents"],
        "fields": ["score"],
        "schema_visible": False,
        "expected_detectors": ["Strategy C"],
        "description": "Converts score from similarity relevance to distance metric (1.0 - score).",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _search_d3_response(ep, res),
    },
    ("D4", "search"): {
        "drift_name": "Nested <-> Flat Structure",
        "endpoints": ["search"],
        "fields": ["filters"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy B"],
        "description": "Replaces nested 'filters' dict parameter with a flat string field 'filter_category'.",
        "apply_schema": lambda schema: _search_d4_schema(schema),
        "request_transform": lambda ep, req: _search_d4_req_transform(req),
        "response_transform": lambda ep, res: res,
    },
    ("D5", "search"): {
        "drift_name": "Silent Null Response",
        "endpoints": ["search", "get_related_documents"],
        "fields": ["id"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B", "Strategy C"],
        "description": "Sets the document ID of the top search result to None.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _search_d5_response(ep, res),
    },
    ("D6", "search"): {
        "drift_name": "Endpoint Deprecation with Fallback",
        "endpoints": ["search"],
        "fields": ["search"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy C"],
        "description": "Marks 'search' deprecated in favor of 'search_v2'; old endpoint returns static unrelated document results.",
        "apply_schema": lambda schema: _deprecate_endpoint(schema, "search"),
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: res,
        "fallback_response": lambda ep, req: {
            "status": "success",
            "results": [
                {
                    "id": "doc_999",
                    "title": "Unrelated Off-Topic Document",
                    "snippet": "This document contains static unrelated information.",
                    "score": 0.5,
                }
            ],
            "total": 1,
            "page": 1,
        },
    },

    # -------------------------------------------------------------------------
    # Email API
    # -------------------------------------------------------------------------
    ("D1", "email"): {
        "drift_name": "Request Field Rename",
        "endpoints": ["send_email"],
        "fields": ["cc"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A"],
        "description": "Renames optional request field 'cc' to 'carbon_copy' in send_email.",
        "apply_schema": lambda schema: _rename_req_field(schema, ["send_email"], "cc", "carbon_copy"),
        "request_transform": lambda ep, req: _rename_dict_key(req, "carbon_copy", "cc"),
        "response_transform": lambda ep, res: res,
    },
    ("D2", "email"): {
        "drift_name": "Response Format Change",
        "endpoints": ["send_email", "get_email", "list_emails"],
        "fields": ["queued_at"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B"],
        "description": "Converts unix epoch timestamp 'queued_at' to an ISO-8601 string in email responses.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _email_d2_response(ep, res),
    },
    ("D3", "email"): {
        "drift_name": "Value Meaning Change",
        "endpoints": ["send_email"],
        "fields": ["send_at"],
        "schema_visible": False,
        "expected_detectors": ["Strategy C"],
        "description": "Reinterprets request 'send_at' timestamp sent in milliseconds (divided by 1000 before handler).",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: _email_d3_req_transform(req),
        "response_transform": lambda ep, res: res,
    },
    ("D4", "email"): {
        "drift_name": "Nested <-> Flat Structure",
        "endpoints": ["send_email"],
        "fields": ["sender"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy B"],
        "description": "Flattens nested 'sender' dict into separate 'sender_email' and 'sender_name' request fields.",
        "apply_schema": lambda schema: _email_d4_schema(schema),
        "request_transform": lambda ep, req: _email_d4_req_transform(req),
        "response_transform": lambda ep, res: res,
    },
    ("D5", "email"): {
        "drift_name": "Silent Null Response",
        "endpoints": ["send_email", "get_email", "list_emails"],
        "fields": ["message_id"],
        "schema_visible": False,
        "expected_detectors": ["Strategy B", "Strategy C"],
        "description": "Sets message_id to None in email responses silently.",
        "apply_schema": lambda schema: None,
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: _email_d5_response(ep, res),
    },
    ("D6", "email"): {
        "drift_name": "Endpoint Deprecation with Fallback",
        "endpoints": ["send_email"],
        "fields": ["send_email"],
        "schema_visible": True,
        "expected_detectors": ["Strategy A", "Strategy C"],
        "description": "Marks 'send_email' deprecated in favor of 'send_email_v2'; old returns success but message is NOT queued in ground truth outbox.",
        "apply_schema": lambda schema: _deprecate_endpoint(schema, "send_email"),
        "request_transform": lambda ep, req: req,
        "response_transform": lambda ep, res: res,
        "fallback_response": lambda ep, req: {
            "status": "success",
            "message_id": "msg_0000",
            "queued_at": 1700000000,
        },
    },
}


# Helper functions for Catalog Schema Modifications & Transformations

def _rename_req_field(schema: dict, endpoints: list, old_name: str, new_name: str) -> None:
    for ep in endpoints:
        req_fields = schema.get("endpoints", {}).get(ep, {}).get("request", {})
        if old_name in req_fields:
            field_def = req_fields.pop(old_name)
            req_fields[new_name] = field_def


def _rename_dict_key(d: dict, old_k: str, new_k: str) -> dict:
    res = dict(d)
    if old_k in res:
        res[new_k] = res.pop(old_k)
    return res


def _deprecate_endpoint(schema: dict, endpoint: str) -> None:
    endpoints = schema.get("endpoints", {})
    if endpoint in endpoints:
        endpoints[endpoint]["deprecated"] = True
        v2_name = f"{endpoint}_v2"
        endpoints[endpoint]["replaced_by"] = v2_name
        endpoints[v2_name] = copy.deepcopy(endpoints[endpoint])


# CRM Helpers
def _crm_d2_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "create_customer" and "created_at" in res:
        res["created_at"] = _epoch_to_iso(res["created_at"])
    elif ep == "update_customer" and "updated_at" in res:
        res["updated_at"] = _epoch_to_iso(res["updated_at"])
    elif ep == "get_customer" and res.get("customer"):
        cust = res["customer"]
        if "created_at" in cust:
            cust["created_at"] = _epoch_to_iso(cust["created_at"])
        if "updated_at" in cust:
            cust["updated_at"] = _epoch_to_iso(cust["updated_at"])
    elif ep == "list_customers" and res.get("customers"):
        for cust in res["customers"]:
            if "created_at" in cust:
                cust["created_at"] = _epoch_to_iso(cust["created_at"])
            if "updated_at" in cust:
                cust["updated_at"] = _epoch_to_iso(cust["updated_at"])
    return res


def _crm_d3_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)

    def _transform_record(record):
        if not isinstance(record, dict):
            return
        if "annual_revenue" in record and isinstance(record["annual_revenue"], (int, float)):
            record["annual_revenue"] = record["annual_revenue"] / 1000.0
        meta = record.get("metadata")
        if isinstance(meta, dict) and "annual_revenue" in meta and isinstance(meta["annual_revenue"], (int, float)):
            meta["annual_revenue"] = meta["annual_revenue"] / 1000.0

    if ep in ("create_customer", "update_customer"):
        _transform_record(res)
    elif ep == "get_customer" and res.get("customer"):
        _transform_record(res["customer"])
    elif ep == "list_customers" and res.get("customers"):
        for cust in res["customers"]:
            _transform_record(cust)
    return res


def _crm_d4_schema(schema: dict) -> None:
    for ep in ["create_customer", "update_customer"]:
        req = schema.get("endpoints", {}).get(ep, {}).get("request", {})
        if "address" in req:
            req.pop("address")
            req["address_street"] = {"type": str, "required": False, "description": "Street address"}
            req["address_city"] = {"type": str, "required": False, "description": "City name"}
            req["address_country"] = {"type": str, "required": False, "description": "Country name"}
            req["address_postal_code"] = {"type": str, "required": False, "description": "Postal code"}


def _crm_d4_req_transform(req: dict) -> dict:
    res = dict(req)
    addr = {}
    for key in ["street", "city", "country", "postal_code"]:
        flat_key = f"address_{key}"
        if flat_key in res:
            addr[key] = res.pop(flat_key)
    if addr:
        res["address"] = addr
    return res


def _crm_d4_res_transform(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)

    def _flatten_addr(record):
        if isinstance(record, dict) and "address" in record and isinstance(record["address"], dict):
            addr = record.pop("address")
            for k, v in addr.items():
                record[f"address_{k}"] = v

    if ep == "get_customer" and res.get("customer"):
        _flatten_addr(res["customer"])
    elif ep == "list_customers" and res.get("customers"):
        for cust in res["customers"]:
            _flatten_addr(cust)
    return res


def _crm_d5_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "get_customer" and res.get("customer"):
        res["customer"]["email"] = None
    elif ep == "list_customers" and res.get("customers"):
        for cust in res["customers"]:
            cust["email"] = None
    return res


# Payment Helpers
def _payment_d2_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "charge_customer" and "amount" in res:
        res["amount"] = f"{float(res['amount']):.2f}"
    elif ep == "refund_customer" and "amount_refunded" in res:
        res["amount_refunded"] = f"{float(res['amount_refunded']):.2f}"
    elif ep == "get_transaction" and res.get("transaction"):
        tx = res["transaction"]
        if "amount" in tx:
            tx["amount"] = f"{float(tx['amount']):.2f}"
        if "refunded_amount" in tx:
            tx["refunded_amount"] = f"{float(tx['refunded_amount']):.2f}"
    elif ep == "list_transactions" and res.get("transactions"):
        for tx in res["transactions"]:
            if "amount" in tx:
                tx["amount"] = f"{float(tx['amount']):.2f}"
            if "refunded_amount" in tx:
                tx["refunded_amount"] = f"{float(tx['refunded_amount']):.2f}"
    return res


def _payment_d3_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "charge_customer" and "amount" in res:
        res["amount"] = float(res["amount"]) * 100.0
    elif ep == "refund_customer" and "amount_refunded" in res:
        res["amount_refunded"] = float(res["amount_refunded"]) * 100.0
    elif ep == "get_transaction" and res.get("transaction"):
        tx = res["transaction"]
        if "amount" in tx:
            tx["amount"] = float(tx["amount"]) * 100.0
        if "refunded_amount" in tx:
            tx["refunded_amount"] = float(tx["refunded_amount"]) * 100.0
    elif ep == "list_transactions" and res.get("transactions"):
        for tx in res["transactions"]:
            if "amount" in tx:
                tx["amount"] = float(tx["amount"]) * 100.0
            if "refunded_amount" in tx:
                tx["refunded_amount"] = float(tx["refunded_amount"]) * 100.0
    return res


def _payment_d4_schema(schema: dict) -> None:
    req = schema.get("endpoints", {}).get("charge_customer", {}).get("request", {})
    if "payment_method" in req:
        req["payment_method"] = {
            "type": dict,
            "required": False,
            "description": "Nested payment instrument object",
            "properties": {
                "type": {"type": str, "required": True, "description": "Payment instrument type"},
                "details": {"type": str, "required": False, "description": "Instrument details"},
            },
        }


def _payment_d4_req_transform(req: dict) -> dict:
    res = dict(req)
    if "payment_method" in res and isinstance(res["payment_method"], dict):
        pm_dict = res.pop("payment_method")
        res["payment_method"] = pm_dict.get("type", "card")
    return res


def _payment_d5_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "charge_customer":
        res["transaction_id"] = None
    elif ep == "refund_customer":
        res["transaction_id"] = None
    elif ep == "get_transaction" and res.get("transaction"):
        res["transaction"]["transaction_id"] = None
    elif ep == "list_transactions" and res.get("transactions"):
        for tx in res["transactions"]:
            tx["transaction_id"] = None
    return res


# Weather Helpers
def _weather_d2_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "get_current_weather" and "humidity" in res:
        res["humidity"] = f"{res['humidity']}%"
    elif ep == "get_forecast" and res.get("forecast"):
        for item in res["forecast"]:
            if "humidity" in item:
                item["humidity"] = f"{item['humidity']}%"
    return res


def _weather_d3_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "get_current_weather" and "wind_speed" in res:
        res["wind_speed"] = round(float(res["wind_speed"]) * 3.6, 2)
    elif ep == "get_forecast" and res.get("forecast"):
        for item in res["forecast"]:
            if "wind_speed" in item:
                item["wind_speed"] = round(float(item["wind_speed"]) * 3.6, 2)
    return res


def _weather_d4_schema(schema: dict) -> None:
    req = schema.get("endpoints", {}).get("get_current_weather", {}).get("request", {})
    req.pop("city", None)
    req.pop("country_code", None)
    req["location"] = {
        "type": dict,
        "required": True,
        "description": "Location object containing city and optional country_code",
        "properties": {
            "city": {"type": str, "required": True, "description": "City name"},
            "country_code": {"type": str, "required": False, "description": "Country code"},
        },
    }


def _weather_d4_req_transform(req: dict) -> dict:
    res = dict(req)
    if "location" in res and isinstance(res["location"], dict):
        loc = res.pop("location")
        if "city" in loc:
            res["city"] = loc["city"]
        if "country_code" in loc:
            res["country_code"] = loc["country_code"]
    return res


def _weather_d5_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "get_current_weather":
        res["temperature"] = None
    elif ep == "get_forecast" and res.get("forecast"):
        for item in res["forecast"]:
            item["temperature"] = None
    return res


# Search Helpers
def _search_d2_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if res.get("results"):
        for item in res["results"]:
            if "score" in item:
                item["score"] = str(item["score"])
    return res


def _search_d3_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if res.get("results"):
        for item in res["results"]:
            if "score" in item and isinstance(item["score"], (int, float)):
                item["score"] = round(1.0 - float(item["score"]), 2)
    return res


def _search_d4_schema(schema: dict) -> None:
    req = schema.get("endpoints", {}).get("search", {}).get("request", {})
    req.pop("filters", None)
    req["filter_category"] = {
        "type": str,
        "required": False,
        "description": "Flat category filter criterion",
    }


def _search_d4_req_transform(req: dict) -> dict:
    res = dict(req)
    if "filter_category" in res:
        cat = res.pop("filter_category")
        res["filters"] = {"category": cat}
    return res


def _search_d5_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if res.get("results") and len(res["results"]) > 0:
        res["results"][0]["id"] = None
    return res


# Email Helpers
def _email_d2_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "send_email" and "queued_at" in res:
        res["queued_at"] = _epoch_to_iso(res["queued_at"])
    elif ep == "get_email" and res.get("email"):
        if "queued_at" in res["email"]:
            res["email"]["queued_at"] = _epoch_to_iso(res["email"]["queued_at"])
    elif ep == "list_emails" and res.get("emails"):
        for item in res["emails"]:
            if "queued_at" in item:
                item["queued_at"] = _epoch_to_iso(item["queued_at"])
    return res


def _email_d3_req_transform(req: dict) -> dict:
    res = dict(req)
    if "send_at" in res and isinstance(res["send_at"], (int, float)):
        res["send_at"] = int(res["send_at"] / 1000)
    return res


def _email_d4_schema(schema: dict) -> None:
    req = schema.get("endpoints", {}).get("send_email", {}).get("request", {})
    req.pop("sender", None)
    req["sender_email"] = {"type": str, "required": False, "description": "Sender email address"}
    req["sender_name"] = {"type": str, "required": False, "description": "Sender display name"}


def _email_d4_req_transform(req: dict) -> dict:
    res = dict(req)
    sender_email = res.pop("sender_email", None)
    sender_name = res.pop("sender_name", None)
    if sender_email or sender_name:
        sender = {}
        if sender_email:
            sender["email"] = sender_email
        if sender_name:
            sender["name"] = sender_name
        res["sender"] = sender
    return res


def _email_d5_response(ep: str, res: dict) -> dict:
    res = copy.deepcopy(res)
    if ep == "send_email":
        res["message_id"] = None
    elif ep == "get_email" and res.get("email"):
        res["email"]["message_id"] = None
    elif ep == "list_emails" and res.get("emails"):
        for item in res["emails"]:
            item["message_id"] = None
    return res


class DriftInjector:
    """Dynamic schema and response drift injection engine."""

    def __init__(self, schedule: Optional[Dict[int, List[Tuple[str, str]]]] = None):
        self._schedule = schedule or {}
        self._tools = dict(_TOOL_MODULES)

        # Store initial snapshots of original schemas and handlers
        self._original_schemas: Dict[str, dict] = {}
        self._original_handlers: Dict[str, Dict[str, Callable]] = {}

        for tool_name, module in self._tools.items():
            self._original_schemas[tool_name] = copy.deepcopy(module.SCHEMA)
            self._original_handlers[tool_name] = {}
            for ep in module.SCHEMA["endpoints"]:
                if hasattr(module, ep):
                    self._original_handlers[tool_name][ep] = getattr(module, ep)

        self._active_drifts: List[dict] = []
        self._drift_log: List[dict] = []
        self._counter = 0
        self._in_task = False
        self._task_label = ""
        self._current_task_index: Optional[int] = None

    def begin_task(self, label: str = "") -> None:
        """Marks entry into an active task boundary."""
        self._in_task = True
        self._task_label = label

    def end_task(self) -> None:
        """Marks exit from an active task boundary."""
        self._in_task = False
        self._task_label = ""

    def on_task_boundary(self, task_index: int) -> List[dict]:
        """Applies scheduled injections at a task boundary."""
        self._current_task_index = task_index
        records = []
        if task_index in self._schedule:
            for drift_id, tool in self._schedule[task_index]:
                rec = self.inject(drift_id, tool, allow_mid_task=True)
                records.append(rec)
        return records

    def active_drifts(self) -> List[dict]:
        """Returns active drift log records."""
        return copy.deepcopy(self._active_drifts)

    def get_drift_log(self) -> List[dict]:
        """Returns a complete deep copy of the drift log records."""
        return copy.deepcopy(self._drift_log)

    def inject(self, drift_id: str, tool: str, allow_mid_task: bool = False) -> dict:
        """Injects a specified drift into a target tool."""
        if tool not in self._tools:
            raise UnknownToolError(f"Unknown tool: '{tool}'")

        key = (drift_id, tool)
        if key not in DRIFT_CATALOG:
            raise InvalidDriftError(f"Drift '{drift_id}' is not defined for tool '{tool}'")

        if self._in_task and not allow_mid_task:
            raise MidTaskInjectionError(
                f"Cannot inject drift '{drift_id}' during active task '{self._task_label}'. "
                "Drift must be injected between tasks."
            )

        spec = DRIFT_CATALOG[key]
        endpoints = spec["endpoints"]
        fields = spec["fields"]

        # Conflict check: check if any target endpoint + field combination is already active
        for active in self._active_drifts:
            if active["tool"] == tool:
                # Check for overlapping endpoints and fields or D6 conflicts
                common_eps = set(endpoints).intersection(set(active["endpoints"]))
                if common_eps:
                    common_fields = set(fields).intersection(set(active["fields"]))
                    if common_fields or drift_id == active["drift_id"]:
                        raise ConflictingDriftError(
                            f"Drift '{drift_id}' on tool '{tool}' conflicts with active drift '{active['drift_id']}'"
                        )

        self._counter += 1
        inj_id = f"inj_{self._counter:04d}"

        record = {
            "injection_id": inj_id,
            "drift_id": drift_id,
            "drift_name": spec["drift_name"],
            "tool": tool,
            "endpoints": list(endpoints),
            "fields": list(fields),
            "schema_visible": spec["schema_visible"],
            "expected_detectors": list(spec["expected_detectors"]),
            "task_index": self._current_task_index if self._in_task else None,
            "description": spec["description"],
        }

        self._active_drifts.append(record)
        self._drift_log.append(copy.deepcopy(record))

        # Apply schema modification on module.SCHEMA if applicable
        module = self._tools[tool]
        spec["apply_schema"](module.SCHEMA)

        # For D6 endpoint deprecation, register <endpoint>_v2 on module
        if drift_id == "D6":
            for ep in endpoints:
                v2_name = f"{ep}_v2"
                orig_h = self._original_handlers[tool][ep]
                setattr(module, v2_name, orig_h)

        # Re-wrap handlers on module to incorporate active drifts
        self._rewrap_tool(tool)

        return copy.deepcopy(record)

    def _rewrap_tool(self, tool_name: str) -> None:
        """Wraps module-level handlers for a tool based on all currently active drifts."""
        module = self._tools[tool_name]
        tool_active_drifts = [d for d in self._active_drifts if d["tool"] == tool_name]

        for ep in self._original_handlers[tool_name]:
            # Find all active drift specs affecting this endpoint
            ep_specs = []
            for ad in tool_active_drifts:
                spec = DRIFT_CATALOG[(ad["drift_id"], tool_name)]
                if ep in spec["endpoints"]:
                    ep_specs.append(spec)

            if not ep_specs:
                # Restore original handler if no active drifts affect this endpoint
                setattr(module, ep, self._original_handlers[tool_name][ep])
                continue

            # Create wrapped handler function
            orig_handler = self._original_handlers[tool_name][ep]
            wrapper = self._create_wrapper(tool_name, ep, orig_handler, ep_specs)
            setattr(module, ep, wrapper)

    def _create_wrapper(self, tool_name: str, ep: str, orig_handler: Callable, ep_specs: List[dict]) -> Callable:
        injector = self

        def wrapped_handler(request=None, **kwargs):
            if request is None:
                request = kwargs
            elif kwargs:
                request = dict(request)
                request.update(kwargs)
            else:
                request = dict(request)

            module = injector._tools[tool_name]

            # 1. Validate against live drifted module.SCHEMA
            errors = module._validate(ep, request)
            if errors:
                return {"status": "error", "errors": errors}

            # 2. Check for D6 fallback response
            for spec in ep_specs:
                if "fallback_response" in spec:
                    return spec["fallback_response"](ep, request)

            # 3. Drop fields not recognized by the live drifted request contract (silent ignore)
            drifted_req_schema = module.SCHEMA.get("endpoints", {}).get(ep, {}).get("request", {})
            curr_req = {k: v for k, v in request.items() if k in drifted_req_schema}

            # 4. Request translation (drifted request contract -> original contract)
            for spec in ep_specs:
                curr_req = spec["request_transform"](ep, curr_req)

            # 5. Invoke original handler while swapping original SCHEMA temporarily
            drifted_schema = module.SCHEMA
            module.SCHEMA = injector._original_schemas[tool_name]
            try:
                response = orig_handler(curr_req)
            finally:
                module.SCHEMA = drifted_schema

            # 5. Response transformation (original response -> drifted contract)
            if response.get("status") == "success":
                for spec in ep_specs:
                    response = spec["response_transform"](ep, response)

            return response

        return wrapped_handler

    def reset(self, ground_truth: bool = False) -> None:
        """Resets all tools to pre-injection original state."""
        for tool_name, module in self._tools.items():
            # Restore original SCHEMA
            module.SCHEMA = copy.deepcopy(self._original_schemas[tool_name])

            # Restore original handlers and remove any *_v2 attributes
            for ep, orig_h in self._original_handlers[tool_name].items():
                setattr(module, ep, orig_h)
                v2_name = f"{ep}_v2"
                if hasattr(module, v2_name):
                    delattr(module, v2_name)

            if ground_truth:
                module._reset_ground_truth()

        self._active_drifts.clear()
        self._counter = 0
        self._in_task = False
        self._task_label = ""
        self._current_task_index = None
