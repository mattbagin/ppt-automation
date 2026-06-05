# Deck Agent

An agentic application that drafts PowerPoint deck **specifications** for a bank's
risk reporting function. An LLM (called via a corporate gateway) composes a structured
deck spec; a deterministic, audited renderer turns that spec into a `.pptx`.

The agent produces a **~60% first draft** that enters an existing human review
workflow. It is a drafting accelerator, not an authoritative producer.

---

## Design principles (why it's built this way)

1. **The model decides structure and content; audited code does the rendering.**
   The LLM never writes arbitrary code that touches data or runs in your environment.
   It emits a declarative deck spec (JSON). This keeps the system reproducible,
   diff-able, and safe for a regulated context.

2. **The model never invents or adjusts figures.** All values come from the data
   layer via read-only tools. There is no `write_data` tool — the agent is
   *structurally* incapable of altering numbers.

3. **Skills are instructional context, not callable tools.** Skills (`SKILL.md`
   files) teach the model *how* to compose a valid spec and choose visualizations.
   Tools are the *actions* the model takes. A small catalog lives in the system
   prompt; full skill bodies load on demand (progressive disclosure) via `load_skill`.

4. **`validate_spec` is the linchpin.** Its error messages are the prompts that
   drive self-correction. Errors are collected (fail-rich), specific, and always
   include valid alternatives at the point of failure.

5. **Plain Python agent loop, no graph framework.** The control flow is a
   mostly-linear pipeline with one retry loop (generate -> validate -> fix). That
   doesn't need LangGraph; a ~150-line loop is more transparent and auditable, and
   carries no third-party dependency/audit burden in a bank environment.

6. **Single source of truth for renderer capabilities.** Layout slot counts, table
   row limits, region dimensions, and style tokens live in ONE place
   (`renderer_capabilities.py`) imported by BOTH the validator and the renderer,
   so the two can never drift.

---

## Project layout

```
deck_agent/
├── README.md
├── requirements.txt
├── run.py                          # CLI entry point (demo / smoke test)
├── deck_agent/
│   ├── __init__.py
│   ├── agent.py                    # the agent loop
│   ├── gateway.py                  # gateway client adapter (FILL IN for your gateway)
│   ├── renderer_capabilities.py    # SINGLE SOURCE OF TRUTH for renderer limits/tokens
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── definitions.py          # tool JSON schemas exposed to the LLM
│   │   ├── data.py                 # get_available_data, fetch_data (STUBS - wire to your sources)
│   │   ├── skills.py               # load_skill + skill catalog
│   │   └── deck.py                 # validate_spec, render_deck dispatch
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── result.py               # ValidationError / ValidationResult
│   │   └── validators.py           # the 4 validation layers
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── system_prompt.py        # build_system_prompt + constants
│   └── skills/                     # progressive-disclosure skill bodies
│       ├── pptx-spec.SKILL.md      # PLACEHOLDER - your schema lives here
│       ├── corporate-style.SKILL.md# PLACEHOLDER
│       └── data-viz.SKILL.md       # PLACEHOLDER
```

---

## What's real vs. what's a stub

This is the **architecture and control flow**, fully wired together. The pieces that
depend on YOUR environment are marked `# TODO` / `STUB` and isolated so you can fill
them in without touching the loop:

- **`gateway.py`** — adapt to your corporate gateway's exact request/response shape.
  Written against the standard Anthropic Messages contract (`tool_use` blocks,
  `stop_reason`, `tool_result`). The two most likely divergence points are flagged.
- **`tools/data.py`** — `get_available_data` / `fetch_data` return mock data. Wire
  these to Bloomberg (`blpapi`), your risk DB, and Excel sources.
- **`deck.py::render_deck_impl`** — the actual python-pptx rendering is stubbed.
  Build this against your frozen spec schema (handled in your other thread).
- **`skills/*.SKILL.md`** — placeholders. Drop in your real skill content.
- **`renderer_capabilities.py`** — example tokens/limits. Replace with your real ones.

---

## Working with this in Claude Code

Suggested first prompts once you've opened the project:

- "Wire `tools/data.py::fetch_data_impl` to our blpapi data pull — here's how we
  currently call it: ..."
- "Implement `render_deck_impl` against this spec schema: ..." (paste your schema)
- "Adapt `gateway.py` to our gateway — here's a sample request/response: ..."
- "Fill in `renderer_capabilities.py` with our real style tokens and layout limits."

The control flow (`agent.py`), validation layers (`validation/`), and prompt
assembly (`prompts/`) should need little change — they're the stable core.

## Run the smoke test

```bash
pip install -r requirements.txt
python run.py            # runs the loop against mock data + a fake gateway
```

The smoke test uses a scripted fake gateway so you can watch the loop, tool dispatch,
and validation feedback work end-to-end before wiring anything real.
