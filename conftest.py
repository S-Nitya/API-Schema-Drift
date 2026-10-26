# conftest.py – Root-level pytest configuration.
#
# Ensures the repository root is on sys.path so that top-level packages
# (agent/, mock_tools/, drift_engine/, workflows/, contracts.py) can be
# imported without any special PYTHONPATH setup.

import importlib
import sys
from pathlib import Path

import pytest

# Add the repo root (this file's directory) to sys.path.
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True)
def _restore_mock_tool_modules():
    """Reload mock tools after each test to prevent global drift leakage."""
    yield
    from mock_tools import crm_api, email_api, payment_api, search_api, weather_api

    for module in (crm_api, payment_api, weather_api, search_api, email_api):
        importlib.reload(module)
