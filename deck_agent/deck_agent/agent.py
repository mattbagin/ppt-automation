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

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .gateway import GatewayResponse

logger = logging.getLogger("deck_agent")

MAX_TURNS = 25  # hard ceiling: prevents runaway loops / cost. Tune to your decks.

# Transient-failure handling for the gateway call. A single network blip against
# a remote corporate gateway should not kill an otherwise-good run.
GATEWAY_MAX_RETRIES = 4          # 4 retries => up to 5 attempts total
GATEWAY_RETRY_BASE_DELAY = 2.0   # seconds; exponential: 2, 4, 8, 16


@dataclass
class AgentResult:
    status: str  # 'success' | 'needs_user_input' | 'max_turns_exceeded' | 'gateway_error'
    output_path: str | None = None
    message: str | None = None
    turns_used: int = 0
    transcript: list[dict] = field(default_factory=list)


def run_deck_agent(
    *,
    user_request: str,
    gateway,
    tools: list[dict],
    tool_implementations: dict[str, Callable],
    system_prompt: str,
    max_turns: int = MAX_TURNS,
    audit_dir: str | None = None,
    gateway_max_retries: int = GATEWAY_MAX_RETRIES,
) -> AgentResult:
    """Drive the deck-generation agent to completion.

    user_request          : the user's brief (topic, references, text, data pointers).
    gateway               : GatewayClient wrapping the corporate gateway.
    tools                 : tool JSON schemas (TOOLS from tools.definitions).
    tool_implementations  : {name: callable} from build_tool_implementations().
    system_prompt         : from build_system_prompt().
    audit_dir             : if set, every run (success OR failure) writes a JSON
                            audit record here — timestamp, brief, status, output
                            path + SHA-256, and the full transcript. This is the
                            auditable record of how a given deck was drafted; in a
                            bank-owned, review-conscious context it is not optional.
    gateway_max_retries   : transient-failure retries for the gateway call.
    """
    messages: list[dict] = [{"role": "user", "content": user_request}]

    def _finish(result: AgentResult) -> AgentResult:
        """Single exit point: attach transcript, persist audit record, return."""
        result.transcript = messages
        if audit_dir:
            _persist_audit_record(audit_dir, user_request, result)
        return result

    for turn in range(max_turns):
        try:
            response: GatewayResponse = _call_gateway_with_retry(
                gateway,
                system=system_prompt,
                messages=messages,
                tools=tools,
                max_tokens=4096,
                max_retries=gateway_max_retries,
            )
        except Exception as exc:  # noqa: BLE001 — surface gateway failure as a result, not a crash
            logger.exception("Gateway call failed after retries")
            return _finish(AgentResult(
                status="gateway_error",
                message=f"Gateway call failed after {gateway_max_retries} retries: {exc}",
                turns_used=turn + 1,
            ))

        # Persist the assistant turn verbatim (tool_use blocks included) so the
        # conversation history stays valid for the next call.
        messages.append({
            "role": "assistant",
            "content": _assistant_content_for_history(response),
        })

        if response.stop_reason != "tool_use":
            # No tool call: the agent is asking a question or reporting it can't
            # proceed (success terminates via render_deck, not a plain text stop).
            return _finish(AgentResult(
                status="needs_user_input",
                message=_extract_text(response),
                turns_used=turn + 1,
            ))

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
            return _finish(AgentResult(
                status="success",
                output_path=terminal["output_path"],
                turns_used=turn + 1,
            ))

    return _finish(AgentResult(
        status="max_turns_exceeded",
        message="Agent did not finish within the turn limit.",
        turns_used=max_turns,
    ))


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


# ---------------------------------------------------------------------------
# Gateway resilience — bounded retry with exponential backoff.
# ---------------------------------------------------------------------------

def _call_gateway_with_retry(
    gateway,
    *,
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
    max_retries: int,
    base_delay: float = GATEWAY_RETRY_BASE_DELAY,
) -> GatewayResponse:
    """Call the gateway, retrying transient failures with exponential backoff.

    The gateway is a remote, paid, network dependency; a single blip should not
    kill an otherwise-good run. After max_retries exhausted, the exception
    propagates so the caller can record a 'gateway_error' result (not crash).

    NOTE: this retries on ANY exception. If your gateway SDK distinguishes
    ret[r]yable (timeout/5xx/429) from fatal (auth/4xx) errors, narrow the except
    so you fail fast on non-transient ones instead of waiting out the backoff.
    """
    attempt = 0
    while True:
        try:
            return gateway.create_message(
                system=system, messages=messages, tools=tools, max_tokens=max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 — see docstring on narrowing this
            attempt += 1
            if attempt > max_retries:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Gateway call failed (attempt %d/%d): %s — retrying in %.0fs",
                attempt, max_retries, exc, delay,
            )
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Audit trail — a durable, tamper-evident record of how a deck was drafted.
# ---------------------------------------------------------------------------

def _persist_audit_record(audit_dir: str, user_request: str, result: AgentResult) -> Path:
    """Write a per-run JSON audit record. Captures successful AND failed runs.

    The output file's SHA-256 ties the audit record to the exact artifact that
    was produced, so a reviewer can confirm the deck on disk is the one this run
    generated. Treat this directory as an audit log: retention/access/PII rules
    should be agreed with whoever owns audit before go-live.
    """
    out_dir = Path(audit_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    run_id = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
    record = {
        "run_id": run_id,
        "timestamp": now.isoformat(timespec="seconds"),
        "user_request": user_request,
        "status": result.status,
        "turns_used": result.turns_used,
        "output_path": result.output_path,
        "output_sha256": _sha256(result.output_path),
        "message": result.message,
        "transcript": result.transcript,
    }

    path = out_dir / f"{run_id}.json"
    # default=str so an unexpected non-serializable object degrades to a string
    # rather than losing the entire audit record.
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote audit record: %s", path)
    return path


def _sha256(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
