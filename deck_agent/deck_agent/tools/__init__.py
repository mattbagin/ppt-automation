"""
Tools package.

build_tool_implementations() wires tool NAMES to their Python implementations,
binding a per-run SkillLoader so skill caching is scoped to a single agent run.
The agent loop dispatches by name against the returned mapping.
"""

from __future__ import annotations

from typing import Callable

from .data import fetch_data_impl, get_available_data_impl
from .deck import render_deck_impl, validate_spec_impl
from .definitions import TOOLS
from .skills import SKILL_CATALOG, SkillLoader

__all__ = ["TOOLS", "SKILL_CATALOG", "SkillLoader", "build_tool_implementations"]


def build_tool_implementations(skill_loader: SkillLoader) -> dict[str, Callable]:
    """Return {tool_name: callable}. One mapping per run (skill_loader is per-run)."""
    return {
        "get_available_data": get_available_data_impl,
        "fetch_data": fetch_data_impl,
        "load_skill": skill_loader.load_skill_impl,
        "validate_spec": validate_spec_impl,
        "render_deck": render_deck_impl,
    }
