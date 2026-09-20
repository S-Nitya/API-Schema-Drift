"""Workflows package initializing and exporting all 12 Task 1.4 multi-step workflows.
"""

from workflows.workflow_01_enterprise_onboarding import run_workflow_01
from workflows.workflow_02_event_refund_notification import run_workflow_02
from workflows.workflow_03_coastal_weather_safety import run_workflow_03
from workflows.workflow_04_venue_forecast_reminder import run_workflow_04
from workflows.workflow_05_cancellation_email_refund import run_workflow_05
from workflows.workflow_06_vip_sponsorship_billing import run_workflow_06
from workflows.workflow_07_emergency_weather_bulletin import run_workflow_07
from workflows.workflow_08_customer_address_update import run_workflow_08
from workflows.workflow_09_equipment_weather_guidelines import run_workflow_09
from workflows.workflow_10_billing_audit_receipt import run_workflow_10
from workflows.workflow_11_venue_contingency_planning import run_workflow_11
from workflows.workflow_12_sponsor_booth_booking import run_workflow_12

WORKFLOW_REGISTRY = {
    "W01": {
        "id": "W01",
        "name": "Onboard new enterprise client, charge setup fee, and send itemized invoice receipt",
        "file": "workflow_01_enterprise_onboarding.py",
        "runner": run_workflow_01,
        "tools": ["crm", "payment", "email"],
        "stakes": "high",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
    "W02": {
        "id": "W02",
        "name": "Process weather-triggered outdoor event ticket refund and notify attendee",
        "file": "workflow_02_event_refund_notification.py",
        "runner": run_workflow_02,
        "tools": ["search", "payment", "email"],
        "stakes": "high",
        "drift_exposure": ["D1", "D2", "D3", "D5", "D6"],
    },
    "W03": {
        "id": "W03",
        "name": "Evaluate Mumbai coastal concert weather conditions and send safety advisory to organizers",
        "file": "workflow_03_coastal_weather_safety.py",
        "runner": run_workflow_03,
        "tools": ["search", "weather", "email"],
        "stakes": "low",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
    "W04": {
        "id": "W04",
        "name": "Check 3-day forecast for Delhi outdoor venue and schedule automated logistical reminder",
        "file": "workflow_04_venue_forecast_reminder.py",
        "runner": run_workflow_04,
        "tools": ["weather", "email"],
        "stakes": "low",
        "drift_exposure": ["D2", "D3", "D5", "D6"],
    },
    "W05": {
        "id": "W05",
        "name": "Inspect attendee email history for cancellation notice, look up customer record, and issue ticket refund",
        "file": "workflow_05_cancellation_email_refund.py",
        "runner": run_workflow_05,
        "tools": ["email", "crm", "payment"],
        "stakes": "high",
        "drift_exposure": ["D2", "D3", "D5", "D6"],
    },
    "W06": {
        "id": "W06",
        "name": "Look up VIP ticketing policy, register VIP sponsor with revenue metadata, and charge package fee",
        "file": "workflow_06_vip_sponsorship_billing.py",
        "runner": run_workflow_06,
        "tools": ["search", "crm", "payment"],
        "stakes": "high",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
    "W07": {
        "id": "W07",
        "name": "Audit active weather alerts in Bengaluru and distribute emergency evacuation bulletin",
        "file": "workflow_07_emergency_weather_bulletin.py",
        "runner": run_workflow_07,
        "tools": ["weather", "search", "email"],
        "stakes": "high",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
    "W08": {
        "id": "W08",
        "name": "Update customer contact profile with new address, send confirmation email, and verify queued dispatch",
        "file": "workflow_08_customer_address_update.py",
        "runner": run_workflow_08,
        "tools": ["crm", "email"],
        "stakes": "low",
        "drift_exposure": ["D1", "D2", "D4", "D5", "D6"],
    },
    "W09": {
        "id": "W09",
        "name": "Check Chennai current weather and retrieve equipment operational guidelines",
        "file": "workflow_09_equipment_weather_guidelines.py",
        "runner": run_workflow_09,
        "tools": ["weather", "search"],
        "stakes": "low",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5"],
    },
    "W10": {
        "id": "W10",
        "name": "Audit customer communication history, fetch account profile, and verify transaction receipt",
        "file": "workflow_10_billing_audit_receipt.py",
        "runner": run_workflow_10,
        "tools": ["email", "crm", "payment"],
        "stakes": "low",
        "drift_exposure": ["D2", "D3", "D5", "D6"],
    },
    "W11": {
        "id": "W11",
        "name": "Evaluate Pune venue current conditions, multi-day forecast, and contingency guidelines",
        "file": "workflow_11_venue_contingency_planning.py",
        "runner": run_workflow_11,
        "tools": ["weather", "search"],
        "stakes": "low",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
    "W12": {
        "id": "W12",
        "name": "Charge booth rental fee to registered sponsor, send confirmation email, and verify message delivery record",
        "file": "workflow_12_sponsor_booth_booking.py",
        "runner": run_workflow_12,
        "tools": ["crm", "payment", "email"],
        "stakes": "high",
        "drift_exposure": ["D1", "D2", "D3", "D4", "D5", "D6"],
    },
}

ALL_WORKFLOWS = list(WORKFLOW_REGISTRY.values())

__all__ = [
    "run_workflow_01",
    "run_workflow_02",
    "run_workflow_03",
    "run_workflow_04",
    "run_workflow_05",
    "run_workflow_06",
    "run_workflow_07",
    "run_workflow_08",
    "run_workflow_09",
    "run_workflow_10",
    "run_workflow_11",
    "run_workflow_12",
    "WORKFLOW_REGISTRY",
    "ALL_WORKFLOWS",
]
