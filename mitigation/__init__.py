"""Mitigation package for API Schema Drift testbed.

Exposes MitigationStrategy base interface, Action directives, PreCallResult, PostCallResult,
and Strategy implementations (Strategy A: SchemaDiffCaching).
"""

from mitigation.base import Action, MitigationStrategy, PostCallResult, PreCallResult
from mitigation.strategy_a import SchemaDiffCaching, compute_schema_hash

__all__ = [
    "Action",
    "MitigationStrategy",
    "PreCallResult",
    "PostCallResult",
    "SchemaDiffCaching",
    "compute_schema_hash",
]
