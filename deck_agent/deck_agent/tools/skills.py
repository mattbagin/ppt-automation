"""
Skill loading (progressive disclosure).

With only 3 skills, you do NOT need a skill-index/registry abstraction. The
three-line catalog below IS the index; it lives in the system prompt always, and
full SKILL.md bodies load on demand via load_skill.

Caching: once a skill is loaded in a run it stays loaded, and the model is told
not to reload it. This gives the uniform "one pattern" interface (good for the
handoff to your team) without re-sending the same skill body every turn.

Practical note from the design discussion: pptx-spec and corporate-style are
effectively needed on almost every run, while data-viz is genuinely conditional
(only when a slide has a chart). The uniform-with-caching approach handles all
three with one mechanism; the model simply loads the always-needed ones early.
"""

from __future__ import annotations

from pathlib import Path

# Catalog: name -> one-line "when to load" description. Goes in the system prompt.
SKILL_CATALOG: dict[str, str] = {
    "pptx-spec": (
        "Defines the deck spec structure: valid element types, layouts, slide "
        "composition. Load before composing any spec."
    ),
    "corporate-style": (
        "Brand palette, fonts, style tokens, layout rules. Load before making any "
        "visual/formatting choice. The ONLY style tokens the renderer supports are "
        "those defined here."
    ),
    "data-viz": (
        "Owns visualization decisioning: chart-type selection for a given data "
        "shape, and chart config production. Load when a slide includes a chart."
    ),
}

_SKILL_DIR = Path(__file__).resolve().parent.parent / "skills"
_SKILL_FILES = {
    "pptx-spec": "pptx-spec.SKILL.md",
    "corporate-style": "corporate-style.SKILL.md",
    "data-viz": "data-viz.SKILL.md",
}


class SkillLoader:
    """Per-run skill loader with caching. One instance per agent run."""

    def __init__(self) -> None:
        self._loaded: set[str] = set()

    def load_skill_impl(self, skill_name: str) -> dict:
        if skill_name not in _SKILL_FILES:
            raise KeyError(
                f"Unknown skill '{skill_name}'. Valid: {sorted(_SKILL_FILES)}"
            )
        if skill_name in self._loaded:
            return {
                "skill_name": skill_name,
                "already_loaded": True,
                "note": "This skill is already loaded in the current session.",
            }
        path = _SKILL_DIR / _SKILL_FILES[skill_name]
        content = path.read_text(encoding="utf-8")
        self._loaded.add(skill_name)
        return {
            "skill_name": skill_name,
            "already_loaded": False,
            "content": content,
        }

    @property
    def loaded(self) -> set[str]:
        return set(self._loaded)
