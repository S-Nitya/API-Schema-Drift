"""Drift Injection Engine for API Schema Drift Evaluation.

Provides dynamic, deterministic schema and response drift injection across all 5 mock tools
(CRM, Payment, Weather, Search, Email) without modifying mock tool source files.

Important Usage Rule for Agent Loop:
Tools must always be called as module attributes (e.g., `crm_api.create_customer(...)`),
never via `from crm_api import create_customer`, to ensure dynamically wrapped handlers are invoked.
"""

from drift_engine.drift_injector import (
    ConflictingDriftError,
    DriftInjector,
    InvalidDriftError,
    MidTaskInjectionError,
    UnknownToolError,
)

__all__ = [
    "DriftInjector",
    "MidTaskInjectionError",
    "ConflictingDriftError",
    "InvalidDriftError",
    "UnknownToolError",
]
