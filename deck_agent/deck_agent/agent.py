"""
The agent loop — the stable core of the system.

The loop IS the "graph": each iteration is one model turn plus tool execution.
The only cycle is implicit — a failed tool (e.g. validate_spec) returns an
is_error result the model reads, revises, and retries. No graph framework needed.

Key properties:
  - Errors are CONVERSATIONAL, not fatal: a failed tool returns a tool_result the
    model can act on, rather than crashing the run. This is what makes the
    validate -> render retry loop work.
  - MAX_TURNS is the cost/safety ceiling against a paid gateway.
  - The terminal condition is singular and explicit: success == render_deck ran
    cleanly. Everything else is an intermediate tool call or a request for input.
  - Per-run transcript persistence (optional) gives an auditable record of how a
    given deck was drafted — valuable in a bank-owned, review-conscious context.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from .gateway import GatewayClient, GatewayResponse

logger = logging.getLogger("deck_agent")

MAX_TURNS = 25  # hard ceiling: prevents runaway loops / cost. Tune to your decks.


@dataclass
class AgentResult:
    status: str  # 'success' | 'needs_user_input' | 'max_turns_exceeded'
    output_path: str | None = None
    message: str | None = None
    turns_used: int = 0
    transcript: list[dict] = field(default_factory=list)


def run_deck_agent(
    *,
    user_request: str,
    gateway: GatewayClient,
    tools: list[dict],
    tool_implementations: dict[str, Callable],
    system_prompt: str,
    max_turns: int = MAX_TURNS,
) -> AgentResult:
    """Drive the deck-generation agent to completion.

    user_request          : the user's brief (topic, references, text, data pointers).
    gateway               : GatewayClient wrapping the corporate gateway.
    tools                 : tool JSON schemas (TOOLS from tools.definitions).
    tool_implementations  : {name: callable} from build_tool_implementations().
    system_prompt         : from build_system_prompt().
    """
    messages: list[dict] = [{"role": "user", "content": user_request}]

    for turn in range(max_turns):
        response: GatewayResponse = gateway.create_message(
            system=system_prompt,
            messages=messages,
            tools=tools,
            max_tokens=4096,
        )

        # Persist the assistant turn verbatim (tool_use blocks included) so the
        # conversation history stays valid for the next call.
        messages.append({
            "role": "assistant",
            "content": _assistant_content_for_history(response),
        })

        if response.stop_reason != "tool_use":
            # No tool call: the agent is asking a question or reporting it can't
            # proceed (success terminates via render_deck, not a plain text stop).
            return AgentResult(
                status="needs_user_input",
                message=_extract_text(response),
                turns_used=turn + 1,
                transcript=messages,
            )

        tool_results = []
        terminal = None

        for block in response.content:
            if block.type != "tool_use":
                continue

            name, args = block.name, (block.input or {})
            logger.info("Agent called tool: %s", name)

            try:
                result = tool_implementations[name](**args)
                payload = json.dumps(result)
                is_error = False
            except Exception as exc:  # noqa: BLE001 — errors are conversational
                logger.exception("Tool %s failed", name)
                payload = json.dumps({"error": str(exc)})
                is_error = True
                result = None

            tool_results.append(_tool_result_block(block.id, payload, is_error))

            # render_deck is terminal — capture a clean success to end the loop.
            if name == "render_deck" and not is_error and result and result.get("rendered"):
                terminal = result

        messages.append({"role": "user", "content": tool_results})

        if terminal is not None:
            return AgentResult(
                status="success",
                output_path=terminal["output_path"],
                turns_used=turn + 1,
                transcript=messages,
            )

    return AgentResult(
        status="max_turns_exceeded",
        message="Agent did not finish within the turn limit.",
        turns_used=max_turns,
        transcript=messages,
    )


# ---------------------------------------------------------------------------
# Helpers — the two spots a gateway variant might require changes.
# ---------------------------------------------------------------------------

def _assistant_content_for_history(response: GatewayResponse) -> list[dict]:
    """Rebuild the assistant content array for message history.

    DIVERGENCE POINT 1: if your gateway preserves raw content faithfully, you can
    append response.raw content directly instead of reconstructing here.
    """
    blocks: list[dict] = []
    for b in response.content:
        if b.type == "text":
            blocks.append({"type": "text", "text": b.text or ""})
        elif b.type == "tool_use":
            blocks.append({
                "type": "tool_use",
                "id": b.id,
                "name": b.name,
                "input": b.input or {},
            })
    return blocks


def _tool_result_block(tool_use_id: str, content: str, is_error: bool) -> dict:
    """Standard Anthropic tool_result shape.

    DIVERGENCE POINT 2: translate here if your gateway expects a different
    tool-result envelope.
    """
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": content,
        "is_error": is_error,
    }


def _extract_text(response: GatewayResponse) -> str:
    return "\n".join(b.text or "" for b in response.content if b.type == "text").strip()
