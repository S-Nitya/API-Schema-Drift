"""Mock Tools Ecosystem for API Schema Drift Evaluation.

Provides 5 deterministic mock tools:
- CRM: Customer management (Salesforce-style)
- Payment: Charges and refunds (Stripe-style)
- Weather: Weather forecasts and current conditions (OpenWeatherMap-style)
- Search: Document searching and relevance scoring (Elasticsearch-style)
- Email: Message dispatch and outbox tracking (SendGrid-style)
"""

from mock_tools.crm_api import (
    SCHEMA as CRM_SCHEMA,
    _inspect_ground_truth as inspect_crm_ground_truth,
    _reset_ground_truth as reset_crm_ground_truth,
    create_customer,
    get_customer,
    list_customers,
    update_customer,
)
from mock_tools.email_api import (
    SCHEMA as EMAIL_SCHEMA,
    _inspect_ground_truth as inspect_email_ground_truth,
    _reset_ground_truth as reset_email_ground_truth,
    get_email,
    list_emails,
    send_email,
)
from mock_tools.payment_api import (
    SCHEMA as PAYMENT_SCHEMA,
    _inspect_ground_truth as inspect_payment_ground_truth,
    _reset_ground_truth as reset_payment_ground_truth,
    charge_customer,
    get_transaction,
    list_transactions,
    refund_customer,
)
from mock_tools.search_api import (
    SCHEMA as SEARCH_SCHEMA,
    _inspect_ground_truth as inspect_search_ground_truth,
    _reset_ground_truth as reset_search_ground_truth,
    get_document,
    get_related_documents,
    search,
)
from mock_tools.weather_api import (
    SCHEMA as WEATHER_SCHEMA,
    _inspect_ground_truth as inspect_weather_ground_truth,
    _reset_ground_truth as reset_weather_ground_truth,
    get_alerts,
    get_current_weather,
    get_forecast,
)

__all__ = [
    # CRM
    "CRM_SCHEMA",
    "create_customer",
    "update_customer",
    "get_customer",
    "list_customers",
    "inspect_crm_ground_truth",
    "reset_crm_ground_truth",
    # Payment
    "PAYMENT_SCHEMA",
    "charge_customer",
    "refund_customer",
    "get_transaction",
    "list_transactions",
    "inspect_payment_ground_truth",
    "reset_payment_ground_truth",
    # Email
    "EMAIL_SCHEMA",
    "send_email",
    "get_email",
    "list_emails",
    "inspect_email_ground_truth",
    "reset_email_ground_truth",
    # Weather
    "WEATHER_SCHEMA",
    "get_current_weather",
    "get_forecast",
    "get_alerts",
    "inspect_weather_ground_truth",
    "reset_weather_ground_truth",
    # Search
    "SEARCH_SCHEMA",
    "search",
    "get_document",
    "get_related_documents",
    "inspect_search_ground_truth",
    "reset_search_ground_truth",
]
