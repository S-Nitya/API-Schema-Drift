"""Optional LLM client abstractions and deterministic scripted components.

The agent loop does not require an LLM. ``ScriptedLLM`` is used for repeatable
tests. ``OpenAICompatClient`` remains optional and imports its SDK only when a
caller explicitly instantiates it.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import List, Optional


def extract_json(text: str) -> dict:
    """Extract a JSON object from *text*, tolerating markdown fences and prose.

    Tries, in order:
    1. Parse the whole string as JSON.
    2. Find a ```...``` or ```json...``` fenced block and parse its content.
    3. Find the first ``{`` to last ``}`` substring and parse that.

    Args:
        text: Raw text that may contain a JSON object.

    Returns:
        Parsed dict.

    Raises:
        ValueError: If no valid JSON object can be extracted.
    """
    # 1. Try the whole string first.
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 2. Look for fenced code blocks (```json or ```).
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. Extract first { ... } span.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from text: {text[:200]!r}")


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    def complete(self, system: str, user: str) -> str:
        """Send a chat completion request and return the assistant's reply.

        Args:
            system: System prompt.
            user: User message.

        Returns:
            The assistant's text response.
        """


class ScriptedLLM(LLMClient):
    """Deterministic LLM twin that replays a fixed sequence of responses.

    Useful for unit tests and experiments that must not make real network calls.

    Args:
        responses: List of strings to return in order.  If more calls are made
            than there are responses, the last response is repeated.

    Attributes:
        llm_calls: Count of calls made so far.
        prompts: List of (system, user) tuples recorded in call order.
    """

    def __init__(self, responses: List[str]) -> None:
        if not responses:
            raise ValueError("responses list must not be empty")
        self._responses = responses
        self.llm_calls: int = 0
        self.prompts: List[tuple] = []

    def complete(self, system: str, user: str) -> str:
        """Return the next scripted response (or repeat the last one).

        Args:
            system: System prompt (recorded but not used for routing).
            user: User message (recorded but not used for routing).

        Returns:
            Pre-set response string.
        """
        self.prompts.append((system, user))
        idx = min(self.llm_calls, len(self._responses) - 1)
        response = self._responses[idx]
        self.llm_calls += 1
        return response


class OpenAICompatClient(LLMClient):
    """Optional adapter for an explicitly configured compatible SDK client.

    No environment variables are read. The optional SDK import is inside
    ``__init__``, so importing ``agent`` works when the SDK is unavailable.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        try:
            from openai import OpenAI  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "The optional 'openai' package is required for OpenAICompatClient."
            ) from exc
        kwargs = {}
        if base_url is not None:
            kwargs["base_url"] = base_url
        if api_key is not None:
            kwargs["api_key"] = api_key
        self._client = OpenAI(**kwargs)
        self._model = model
        self.llm_calls: int = 0

    def complete(self, system: str, user: str) -> str:
        """Send a temperature-zero completion through the optional SDK."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        self.llm_calls += 1
        return response.choices[0].message.content
