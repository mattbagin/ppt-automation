"""
Validation result types.

The three fields per error do deliberate work and drive the self-correction loop:
  - path      : WHERE in the spec the problem is, so the model edits the right
                element rather than the whole spec, e.g. "slides[3].elements[1]".
  - problem   : WHAT is wrong, in plain language.
  - fix_hint  : WHAT is valid / how to correct it. This is the field most
                validators omit and the one that most determines whether the
                model recovers next turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationError:
    path: str
    problem: str
    fix_hint: str


@dataclass
class ValidationResult:
    ok: bool
    errors: list[ValidationError] = field(default_factory=list)

    def to_tool_result(self) -> dict:
        """Serialize for return as a tool_result the model will read."""
        if self.ok:
            return {"ok": True}
        return {
            "ok": False,
            "error_count": len(self.errors),
            "errors": [
                {"path": e.path, "problem": e.problem, "fix": e.fix_hint}
                for e in self.errors
            ],
        }
