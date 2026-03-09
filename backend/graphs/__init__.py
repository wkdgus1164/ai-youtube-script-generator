"""Auto-discover graph modules and expose public API.

On import, this package automatically imports all graph modules (except
infrastructure modules) so their @register_graph decorators fire and
populate the registry.

Adding a new graph:
    1. Create backend/graphs/my_agent.py
    2. Decorate the builder with @register_graph("my-agent", description="...")
    3. That's it — no other file needs to be modified.

Responsibility: Auto-discovery and public API surface
Dependencies: graphs/registry.py (via auto-imported modules)
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from graphs.registry import get_available_models, get_graph

# Infrastructure modules that should not be auto-imported as graph providers
_INFRA_MODULES = {"registry", "state", "llm"}

_pkg_dir = Path(__file__).parent
for _module_info in pkgutil.iter_modules([str(_pkg_dir)]):
    if _module_info.name not in _INFRA_MODULES:
        importlib.import_module(f"graphs.{_module_info.name}")

__all__ = ["get_graph", "get_available_models"]
