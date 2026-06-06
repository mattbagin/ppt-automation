# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this is

**Deck Agent** is an agentic application that drafts PowerPoint deck
**specifications** for a bank's risk reporting function. An LLM (called through a
corporate gateway) composes a structured, declarative deck spec (JSON); a
deterministic, audited renderer turns that spec into a `.pptx`.

It is a **drafting accelerator**, not an authoritative producer. The target
output is a **~60% first draft** that enters an existing human review workflow.
Visible gaps and flagged uncertainties are acceptable output, not failures.

This repository is a **scaffold**: the architecture and control flow are fully
wired together and runnable, but the pieces that depend on the corporate
environment are deliberately stubbed (see "Real vs. stub" below). It is not
expected to produce real decks until those stubs are filled in.

## Repository layout

The Python package is nested one level down, under `deck_agent/`:

```
deck_agent/                         # repo-level project dir (run commands from here)
├── README.md                       # design rationale — read this first
├── requirements.txt
├── run.py                          # CLI entry point / smoke test (fake gateway)
└── deck_agent/                     # the importable package
    ├── agent.py                    # the agent loop (stable core)
    ├── gateway.py                  # gateway client adapter  [STUB]
    ├── renderer_capabilities.py    # SINGLE SOURCE OF TRUTH for limits + style tokens
    ├── tools/
    │   ├── definitions.py          # tool JSON schemas exposed to the LLM
    │   ├── data.py                 # get_available_data / fetch_data  [STUB: mock data]
    │   ├── skills.py               # load_skill + skill catalog
    │   └── deck.py                 # validate_spec + render_deck (renderer [STUB])
    ├── validation/
    │   ├── result.py               # ValidationError / ValidationResult
    │   └── validators.py           # the 4 validation layers
    ├── prompts/
    │   └── system_prompt.py        # build_system_prompt + prompt constants
    └── skills/                     # progressive-disclosure skill bodies  [PLACEHOLDER]
        ├── pptx-spec.SKILL.md
        ├── corporate-style.SKILL.md
        └── data-viz.SKILL.md
```

## Running it

```bash
cd deck_agent                 # the package is importable from here
pip install -r requirements.txt
python run.py                 # runs the loop against mock data + a scripted fake gateway
```

`run.py` uses a `FakeGateway` that returns a fixed sequence of turns and
deliberately makes one mistake first (a bad `data_key`) to demonstrate the
validate → self-correct → render loop. It does **not** call any model. A
successful run prints `STATUS: success` and writes a `.pptx` under
`deck_agent/output/`.

There is no test suite yet (see "Known gaps").

## Architecture and the rules that hold it together

Read `deck_agent/README.md` for the full rationale. The non-negotiable
invariants — preserve these when changing code:

1. **The model decides structure and content; audited code does the rendering.**
   The LLM emits a declarative JSON spec. It never writes code that touches data
   or runs in the environment.
2. **The model never invents or adjusts figures.** All values come from the data
   layer via read-only tools. There is intentionally **no `write_data` tool** —
   the agent is structurally incapable of altering numbers. Do not add one.
3. **Skills are instructional context, not callable tools.** `SKILL.md` files
   teach the model *how* to compose a valid spec. Tools are the *actions*. A
   three-line catalog lives in the system prompt; full bodies load on demand via
   `load_skill` (progressive disclosure).
4. **`validate_spec` is the linchpin.** Its error messages are the prompts that
   drive self-correction. Each error carries `path` (where), `problem` (what),
   and `fix` (a valid alternative). Keep all three populated and specific — the
   `fix` hint is what determines whether the model recovers next turn.
5. **`render_deck` re-validates internally** and refuses to render an invalid
   spec, regardless of what the model did. "Render only valid specs" is a
   property of the *system*, not behaviour trusted to the model.
6. **Single source of truth for renderer capabilities.** Layout slot counts,
   table row limits, region dimensions, and style tokens live ONLY in
   `renderer_capabilities.py`, imported by BOTH the validator and the renderer so
   the two cannot drift. Never duplicate these values elsewhere.

## Control flow

`agent.py::run_deck_agent` is a plain Python loop — no graph framework. Each
iteration is one model turn plus tool execution:

- The loop calls `gateway.create_message`, appends the assistant turn to history,
  then dispatches every `tool_use` block to its implementation.
- **Tool errors are conversational, not fatal.** A failing tool returns an
  `is_error` `tool_result` the model reads and acts on (this is what makes the
  validate → render retry loop work). It does not crash the run.
- **Gateway calls are retried** with bounded exponential backoff
  (`_call_gateway_with_retry`). After retries are exhausted the run ends as
  `gateway_error` rather than crashing. The retry currently catches any
  exception — narrow it to the gateway SDK's retryable errors (timeout/5xx/429)
  once that SDK is wired, so non-transient failures (auth/4xx) fail fast.
- **The only terminal success is a clean `render_deck`.** A plain text response
  (no tool call) ends the run as `needs_user_input`. `MAX_TURNS` (25) is the
  cost/safety ceiling.
- **Audit trail.** Pass `audit_dir=` to `run_deck_agent` and every run (success
  or failure) writes a JSON record: timestamp, brief, status, output path +
  SHA-256, and the full transcript. Treat that directory as an audit log —
  agree retention/access/PII rules with audit before go-live.

The validation layers run cheap-and-structural first, expensive-and-semantic
last (`validators.py`): (1) schema/structural, (2) closed vocabulary, (3)
referential integrity, (4) renderability (shape-fit, capacity, layout-slot fit).
Layers fail-rich within a layer (collect all errors) and fail-fast between layers
where a later layer would be meaningless.

## Real vs. stub — where to make changes

The stable core (`agent.py`, `validation/`, `prompts/`) should need little
change. The environment-specific seams, each isolated so you can fill them in
without touching the loop:

| Component | Status | What to do |
|-----------|--------|------------|
| `gateway.py::GatewayClient.create_message` | **STUB** (raises) | Wire to the corporate gateway. Written against the Anthropic Messages contract; `normalize_anthropic_content` helps. Two flagged divergence points: content-block fidelity on the round-trip, and the tool_result envelope shape. |
| `tools/data.py` | **STUB** (`_MANIFEST` mock) | Wire `get_available_data` / `fetch_data` to real sources (blpapi, risk DB, Excel). Keep the metadata shape (`shape`, `row_count`, `period_count`) — the validator's renderability layer checks against it. |
| `tools/deck.py::_render` | **STUB** (minimal pptx) | Implement the audited python-pptx renderer against the frozen spec schema. Add render-time precondition assertions as a validator/renderer drift backstop. |
| `renderer_capabilities.py` | **EXAMPLE values** | Replace tokens/limits/layouts with the real corporate ones. |
| `skills/*.SKILL.md` | **PLACEHOLDER** | Drop in the real spec schema, brand guidelines, and viz rules. |

When wiring a stub, do not change the tool's *signature or contract* — only the
body. The loop and validator depend on the contracts, not the implementations.

## Conventions

- Python 3.11+, `from __future__ import annotations` at the top of modules,
  standard-library-only core (the loop needs no third-party deps; `python-pptx`
  is only for the renderer).
- Keep tool implementations pure-ish and deterministic; side effects (file
  writes) live in `render_deck` only.
- Style tokens, layouts, and element types are a **closed vocabulary**. If you
  add one, add it in `renderer_capabilities.py` AND document it in the matching
  `SKILL.md` — the model may only use what is listed.

## Known gaps before this is production-ready

Still open, to close during the corporate build-out:

- **No automated test suite.** The validators are pure functions and the
  safety-critical component — they want unit coverage per layer and per error
  path. `run.py` is a demo, not coverage.
- **No credential/secret handling in the gateway.** Document how secrets reach
  `GatewayClient` (env vars / secret manager, never literals). `.gitignore`
  already excludes `.env`.
- **Skill names are declared in three places** (`definitions.py` `load_skill`
  enum, `SKILL_CATALOG`, `_SKILL_FILES`) and can drift — derive from one source.
- **Dependencies are unpinned**; consider a lockfile / `pyproject.toml`.
- **`chart_type` inconsistency**: the `data-viz` skill emits it but the schema
  and validator don't account for it — reconcile when the schema is frozen.

Addressed in this scaffold (previously open): `output_name` path-traversal
(sanitised in `deck.py`), gateway transient-failure retry (`agent.py`), and
transcript/audit persistence (`audit_dir`).
