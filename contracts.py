"""Shared contracts for Agent Loop and Mitigation Strategies.

Defines the MitigationStrategy interface that all strategy implementations must satisfy,
along with the data transfer objects used in the pre-call / post-call protocol.

This file is shared with the Strategy A developer.  Any changes require sign-off from
both teams.
"""

import copy
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class Action(str, Enum):
    """Decision returned by a MitigationStrategy hook."""

    PROCEED = "proceed"
    REBUILD = "rebuild"
    HALT = "halt"


@dataclass
class PreCallResult:
    """Result returned by MitigationStrategy.pre_call().

    Attributes:
        action: What the agent loop should do next.
        rebuilt_request: Replacement request dict (only for REBUILD action).
        new_schema: Replacement schema snapshot to adopt (only for REBUILD action).
        field_mapping: Mapping of old -> new field names (hint for RequestBuilder).
        reason: Human-readable explanation for logging.
    """

    action: Action
    rebuilt_request: Optional[Dict] = None
    new_schema: Optional[Dict] = None
    field_mapping: Dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class PostCallResult:
    """Result returned by MitigationStrategy.post_call().

    Attributes:
        action: What the agent loop should do next.
        response: Replacement response dict (PROCEED only; None means use the raw response).
        new_schema: Replacement schema snapshot to adopt (only for REBUILD action).
        reason: Human-readable explanation for logging.
    """

    action: Action
    response: Optional[Dict] = None
    new_schema: Optional[Dict] = None
    reason: str = ""


class MitigationStrategy(ABC):
    """Abstract base class for all schema-drift mitigation strategies.

    The agent loop calls:
        on_schema_read  -- once per tool when the session-start snapshot is taken.
        pre_call        -- before each tool invocation.
        post_call       -- after each tool invocation.
        reset           -- at the start of each run (or when the harness requests it).
        stats           -- to retrieve aggregate metrics.
    """

    #: Short identifier shown in run-end events and reports.
    name: str = "unnamed"

    def on_schema_read(self, tool: str, schema: Dict) -> None:
        """Called once per tool when the session-start snapshot is taken.

        Strategy A uses this hook to prime its schema-diff cache.
        Default implementation is a no-op.

        Args:
            tool: Tool name (e.g. "crm").
            schema: Deep copy of the schema snapshot for that tool.
        """

    @abstractmethod
    def pre_call(self, tool: str, endpoint: str, request: Dict) -> PreCallResult:
        """Called before a tool endpoint is invoked.

        Args:
            tool: Tool name.
            endpoint: Endpoint name within the tool.
            request: The request dict the agent loop is about to send.

        Returns:
            PreCallResult with an Action and any rebuild hints.
        """

    def post_call(
        self, tool: str, endpoint: str, request: Dict, response: Dict
    ) -> PostCallResult:
        """Called after a tool endpoint returns.

        Default implementation always proceeds with the raw response.

        Args:
            tool: Tool name.
            endpoint: Endpoint name.
            request: The request dict that was sent.
            response: The raw response dict returned by the tool.

        Returns:
            PostCallResult with an Action and optional modified response.
        """
        return PostCallResult(action=Action.PROCEED, response=response)

    @abstractmethod
    def reset(self) -> None:
        """Resets any accumulated state so a fresh run can begin."""

    @abstractmethod
    def stats(self) -> Dict:
        """Returns a dict of aggregate metrics collected during this session."""


class NoOpMitigation(MitigationStrategy):
    """Baseline (no-mitigation) strategy.

    pre_call always returns PROCEED, so the agent sees every tool call
    through the drifted schema without any correction.  This is the
    control condition against which Strategies A, B, and C are measured.
    """

    name: str = "baseline"

    def pre_call(self, tool: str, endpoint: str, request: Dict) -> PreCallResult:
        """Always proceed without any modification."""
        return PreCallResult(action=Action.PROCEED)

    def reset(self) -> None:
        """No state to reset."""

    def stats(self) -> Dict:
        """No metrics for baseline."""
        return {}
