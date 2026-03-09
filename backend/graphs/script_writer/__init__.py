"""script_writer package init: importing graph.py triggers @register_graph."""
from __future__ import annotations

from graphs.script_writer import graph as _graph  # noqa: F401 — side-effect import
