"""Base interface for all mitigation strategies in the schema drift testbed.

Defines the core MitigationStrategy abstract class and structured result dataclasses
consumed by the agent loop, baseline, Strategy A, Strategy B, and Strategy C.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


class Action:
    """Pre-call and post-call action directives returned to the agent."""
    PROCEED: str = "PROCEED"
    RELOAD_SCHEMA: str = "RELOAD_SCHEMA"
    HALT: str = "HALT"
    RETRY: str = "RETRY"


@dataclass
class PreCallResult:
    """Result returned by pre_call mitigation inspection.

    Attributes:
        action: Directive for the agent ('PROCEED' or 'RELOAD_SCHEMA').
        drift_detected: Boolean indicating whether drift was detected.
        old_hash: Previous canonical schema hash (if known).
        new_hash: Current live canonical schema hash.
        schema: Live schema snapshot after check/reload.
        diff: Structured diff between cached snapshot and live schema (if drift detected).
        reload_message: Human-readable message explaining the change for agent context injection.
    """
    action: str = Action.PROCEED
    drift_detected: bool = False
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    diff: Optional[Dict[str, Any]] = None
    reload_message: Optional[str] = None


@dataclass
class PostCallResult:
    """Result returned by post_call mitigation inspection.

    Attributes:
        action: Directive for the agent (default 'PROCEED').
        drift_detected: Boolean indicating whether drift was detected in response.
        response: Sanitized or verified response dictionary.
        message: Informational message or warning.
    """
    action: str = Action.PROCEED
    drift_detected: bool = False
    response: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


class MitigationStrategy(ABC):
    """Abstract base class for all mitigation strategies.

    Contract:
        - pre_call is evaluated before dispatching a request to a mock tool.
        - post_call is evaluated after receiving a response from a mock tool.
        - stats exposes per-instance instrumentation counters.
    """

    @abstractmethod
    def pre_call(
        self,
        tool: Union[str, Any],
        endpoint: str,
        request: Dict[str, Any],
    ) -> PreCallResult:
        """Inspects tool and request prior to execution.

        Args:
            tool: Tool identifier (str name e.g. 'crm' or module object).
            endpoint: Name of the endpoint being invoked.
            request: The outbound request payload.

        Returns:
            PreCallResult with action directive and drift details.
        """
        pass

    def post_call(
        self,
        tool: Union[str, Any],
        endpoint: str,
        request: Dict[str, Any],
        response: Dict[str, Any],
    ) -> PostCallResult:
        """Inspects response after tool execution (default pass-through).

        Args:
            tool: Tool identifier (str name e.g. 'crm' or module object).
            endpoint: Name of the endpoint invoked.
            request: Outbound request payload sent to the tool.
            response: Inbound response payload returned by the tool.

        Returns:
            PostCallResult with pass-through action='PROCEED'.
        """
        return PostCallResult(
            action=Action.PROCEED,
            drift_detected=False,
            response=response,
            message=None,
        )

    @property
    @abstractmethod
    def stats(self) -> Dict[str, Any]:
        """Returns instrumentation counters for this strategy instance."""
        pass

    def reset_stats(self) -> None:
        """Resets instrumentation counters for this strategy instance."""
        pass
