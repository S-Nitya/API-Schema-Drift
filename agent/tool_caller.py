"""agent/tool_caller.py – Call-time tool dispatch (Rule R2).

All tool calls go through ToolCaller which resolves module references at call time
via ``importlib.import_module``.  This ensures that drift-injected handler wrappers
(set on the module object) are always invoked instead of a stale reference captured
at import time.
"""

import copy
import importlib
from typing import Dict, List, Optional

# Canonical map from tool name to fully-qualified module path.
_DEFAULT_TOOL_MODULE_MAP: Dict[str, str] = {
    "crm": "mock_tools.crm_api",
    "payment": "mock_tools.payment_api",
    "weather": "mock_tools.weather_api",
    "search": "mock_tools.search_api",
    "email": "mock_tools.email_api",
}


class ToolCaller:
    """Dispatches tool endpoint calls at call time via importlib.

    Design rules (R2):
    - Handlers are looked up as ``getattr(module, endpoint)`` at the moment of
      the call so that drift-injected wrappers are always invoked.
    - ``get_schema(tool)`` is the *only* place that reads ``module.SCHEMA``; the
      agent loop and Strategy A both obtain live schemas through this method.
    - A fake-module dict can be injected via the constructor for unit tests
      (no network/import required).

    Args:
        fake_modules: Optional dict mapping tool name -> fake module object.
            When provided, real module imports are bypassed (test mode).
        tool_module_map: Optional override for the tool->module-path map.
    """

    def __init__(
        self,
        fake_modules: Optional[Dict[str, object]] = None,
        tool_module_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self._tool_module_map: Dict[str, str] = tool_module_map or dict(
            _DEFAULT_TOOL_MODULE_MAP
        )
        self._fake_modules: Dict[str, object] = fake_modules or {}

    def tool_names(self) -> List[str]:
        """Return the sorted list of known tool names.

        Returns:
            List of tool names.
        """
        return sorted(self._tool_module_map.keys())

    def module(self, tool: str) -> object:
        """Return the module object for *tool*, looking it up at call time.

        If a fake module was injected for this tool the fake is returned instead.

        Args:
            tool: Tool name.

        Returns:
            Module object.

        Raises:
            KeyError: If *tool* is not in the tool map.
        """
        if tool in self._fake_modules:
            return self._fake_modules[tool]
        module_path = self._tool_module_map[tool]
        return importlib.import_module(module_path)

    def get_schema(self, tool: str) -> Dict:
        """Return a deep copy of the *live* ``module.SCHEMA`` for *tool*.

        This is the central schema accessor used both by the agent (for session-start
        snapshots) and by Strategy A (for drift detection).

        Args:
            tool: Tool name.

        Returns:
            Deep copy of the module-level SCHEMA dict.

        Raises:
            KeyError: If *tool* is not recognised.
            AttributeError: If the module does not expose a SCHEMA attribute.
        """
        mod = self.module(tool)
        return copy.deepcopy(mod.SCHEMA)

    def call(self, tool: str, endpoint: str, request: Dict) -> Dict:
        """Invoke *endpoint* on *tool* with *request* at call time.

        Looks up the handler via ``getattr(module, endpoint)`` each time so that
        drift-injected wrappers are always used.

        Args:
            tool: Tool name.
            endpoint: Endpoint function name on the module.
            request: Request payload dict.

        Returns:
            Response dict from the handler.

        Raises:
            AttributeError: If the endpoint does not exist on the module.
            Exception: Any exception raised by the handler is propagated.
        """
        mod = self.module(tool)
        handler = getattr(mod, endpoint)
        return handler(request)
