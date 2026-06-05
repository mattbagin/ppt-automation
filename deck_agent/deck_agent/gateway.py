"""
Gateway client adapter.

The agent loop depends only on the small interface defined here, so swapping in
your real corporate gateway is a localized change. Written against the standard
Anthropic Messages contract (tool_use content blocks, stop_reason, tool_result
blocks in a user turn).

TWO LIKELY DIVERGENCE POINTS for a corporate proxy (flagged so you know where to
look first if something breaks):

  1. CONTENT BLOCK FIDELITY on the round-trip. The loop appends the assistant's
     `content` (including tool_use blocks) straight back into messages. If your
     gateway rewrites or strips that shape, add a small adapter in
     `GatewayClient.create_message` to reconstruct valid history.

  2. TOOL_RESULT ENVELOPE. The loop builds tool_result blocks in a user message,
     keyed by tool_use_id. If your gateway expects a different tool-result format,
     translate it in the loop's `_tool_result_block` (agent.py) or here.

We normalize responses into a small dataclass so the loop never touches gateway
specifics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContentBlock:
    """Normalized content block. type is 'text' or 'tool_use'."""
    type: str
    text: str | None = None
    # tool_use fields:
    id: str | None = None
    name: str | None = None
    input: dict | None = None


@dataclass
class GatewayResponse:
    content: list[ContentBlock]
    stop_reason: str  # 'tool_use' | 'end_turn' | ...
    raw: Any = None    # keep the raw payload for transcript/debugging


class GatewayClient:
    """Adapter around your corporate LLM gateway.

    Replace the body of create_message with a real call. The method must:
      - send system, messages, tools, max_tokens
      - return a GatewayResponse with normalized content blocks and stop_reason
    """

    def __init__(self, model: str, **client_kwargs: Any) -> None:
        self.model = model
        self._client_kwargs = client_kwargs
        # TODO: construct your gateway/SDK client here.

    def create_message(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
    ) -> GatewayResponse:
        # TODO: implement against your gateway. Example shape if it speaks the
        # Anthropic SDK:
        #
        #   resp = self._sdk.messages.create(
        #       model=self.model, system=system, messages=messages,
        #       tools=tools, max_tokens=max_tokens,
        #   )
        #   blocks = [_normalize(b) for b in resp.content]
        #   return GatewayResponse(content=blocks, stop_reason=resp.stop_reason, raw=resp)
        raise NotImplementedError(
            "Wire GatewayClient.create_message to your corporate gateway."
        )


def normalize_anthropic_content(raw_content: list) -> list[ContentBlock]:
    """Helper to convert Anthropic-shaped content blocks into ContentBlock.
    Use inside create_message once you have a real response."""
    out: list[ContentBlock] = []
    for b in raw_content:
        btype = getattr(b, "type", None) or b.get("type")
        if btype == "text":
            out.append(ContentBlock(type="text",
                                    text=getattr(b, "text", None) or b.get("text")))
        elif btype == "tool_use":
            out.append(ContentBlock(
                type="tool_use",
                id=getattr(b, "id", None) or b.get("id"),
                name=getattr(b, "name", None) or b.get("name"),
                input=getattr(b, "input", None) or b.get("input"),
            ))
    return out
