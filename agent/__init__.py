"""agent/__init__.py – Public API for the agent package.

Exports the main classes and helpers used by experiment harnesses, tests,
and the dashboard.
"""

from agent.agent_loop import Agent, RunResult, StepResult
from agent.event_log import EventLog
from agent.llm import (
    LLMClient,
    OpenAICompatClient,
    ScriptedLLM,
    extract_json,
)
from agent.planner import LLMPlanner, Plan, PlanError, PlanStep, ScriptedPlanner
from agent.request_builder import LLMRequestBuilder, ScriptedRequestBuilder
from agent.schema_memory import SchemaMemory, jsonable
from agent.tool_caller import ToolCaller

__all__ = [
    # Core loop
    "Agent",
    "RunResult",
    "StepResult",
    # Schema
    "SchemaMemory",
    "jsonable",
    # Tool caller
    "ToolCaller",
    # LLM
    "LLMClient",
    "OpenAICompatClient",
    "ScriptedLLM",
    "extract_json",
    # Planner
    "Plan",
    "PlanStep",
    "PlanError",
    "LLMPlanner",
    "ScriptedPlanner",
    # Builder
    "LLMRequestBuilder",
    "ScriptedRequestBuilder",
    # Log
    "EventLog",
]
