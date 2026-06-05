"""
Entry point / smoke test.

Runs the full agent loop against MOCK data and a SCRIPTED FAKE gateway, so you can
watch the loop, tool dispatch, and validation feedback work end-to-end before
wiring anything real.

The fake gateway deliberately makes ONE mistake first (references a non-existent
data_key) to demonstrate the self-correction loop: validate_spec returns a
structured error, and the fake "model" reads it and fixes the spec on the next turn.

Run:
    python run.py

To run with your real gateway, replace FakeGateway with deck_agent.gateway.GatewayClient
and provide your model id / credentials.
"""

from __future__ import annotations

import json
import logging

from deck_agent.agent import run_deck_agent
from deck_agent.gateway import ContentBlock, GatewayResponse
from deck_agent.prompts import build_system_prompt
from deck_agent.tools import TOOLS, SkillLoader, build_tool_implementations

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


# ---------------------------------------------------------------------------
# A scripted fake gateway: returns a fixed sequence of turns regardless of input.
# This is ONLY for the smoke test — it does not call any model.
# ---------------------------------------------------------------------------

class FakeGateway:
    def __init__(self) -> None:
        self._turn = 0

    def create_message(self, *, system, messages, tools, max_tokens=4096) -> GatewayResponse:
        self._turn += 1

        if self._turn == 1:
            # Discover data first.
            return _tool_use("get_available_data", {}, "tu_1")

        if self._turn == 2:
            # Load the spec skill.
            return _tool_use("load_skill", {"skill_name": "pptx-spec"}, "tu_2")

        if self._turn == 3:
            # First attempt: WRONG — references a data_key that doesn't exist.
            bad_spec = {
                "slides": [
                    {
                        "layout": "table_and_chart",
                        "elements": [
                            {"type": "title", "text": "NII Sensitivity"},
                            {"type": "table", "data_key": "nii_sensitivity", "style": "risk_standard"},
                            {"type": "chart", "data_key": "nii_ts_DOES_NOT_EXIST", "style": "corporate_ts"},
                        ],
                    }
                ]
            }
            return _tool_use("validate_spec", {"spec": bad_spec}, "tu_3")

        if self._turn == 4:
            # Self-corrected: fixed the bad data_key. Validate again.
            good_spec = _good_spec()
            return _tool_use("validate_spec", {"spec": good_spec}, "tu_4")

        if self._turn == 5:
            # Validation passed -> render.
            return _tool_use(
                "render_deck",
                {"spec": _good_spec(), "output_name": "irrbb_monthly"},
                "tu_5",
            )

        # Fallback: end turn.
        return GatewayResponse(
            content=[ContentBlock(type="text", text="Done.")],
            stop_reason="end_turn",
        )


def _good_spec() -> dict:
    return {
        "slides": [
            {
                "layout": "table_and_chart",
                "elements": [
                    {"type": "title", "text": "NII Sensitivity"},
                    {"type": "table", "data_key": "nii_sensitivity", "style": "risk_standard"},
                    {"type": "chart", "data_key": "nii_ts", "style": "corporate_ts"},
                    {"type": "text", "text": "Draft commentary — review figures.", "style": "body"},
                ],
            },
            {
                "layout": "commentary",
                "elements": [
                    {"type": "title", "text": "Key Takeaways"},
                    {"type": "text", "text": "[DRAFT] Flag: confirm EVE figure with desk.", "style": "body"},
                ],
            },
        ]
    }


def _tool_use(name: str, args: dict, tu_id: str) -> GatewayResponse:
    return GatewayResponse(
        content=[ContentBlock(type="tool_use", id=tu_id, name=name, input=args)],
        stop_reason="tool_use",
    )


def main() -> None:
    skill_loader = SkillLoader()
    result = run_deck_agent(
        user_request="Draft the monthly IRRBB deck: NII sensitivity table + NII time series, plus a takeaways slide.",
        gateway=FakeGateway(),
        tools=TOOLS,
        tool_implementations=build_tool_implementations(skill_loader),
        system_prompt=build_system_prompt(),
    )

    print("\n" + "=" * 60)
    print(f"STATUS      : {result.status}")
    print(f"TURNS USED  : {result.turns_used}")
    print(f"OUTPUT PATH : {result.output_path}")
    print(f"SKILLS LOADED: {sorted(skill_loader.loaded)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
