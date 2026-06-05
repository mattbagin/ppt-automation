"""
Tool definitions exposed to the LLM via the gateway.

Design notes:
  - Tools are deterministic, auditable ACTIONS. Skills are instructional context
    (loaded via load_skill). The model never sees raw credentials and references
    data only by key.
  - There is deliberately NO write_data / modify_data tool. The agent is
    structurally incapable of altering figures.
  - get_available_data before fetch_data mirrors discover-then-detail: the model
    discovers keys rather than guessing them.
  - validate_spec is separate from render_deck so the model has a cheap,
    side-effect-free way to fail and self-correct before anything is written.
  - load_skill uses an enum so the model can't invent a skill name (same
    closed-vocabulary discipline as style tokens).
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "get_available_data",
        "description": (
            "List the data series available for this deck, with metadata. "
            "Call this FIRST to discover what data exists before planning slides. "
            "Returns keys, descriptions, units, periods, and shape (scalar/series/"
            "table/matrix). Never assume a data key — always discover it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic_filter": {
                    "type": "string",
                    "description": "Optional keyword to narrow results, e.g. 'NII', 'EVE', 'liquidity'.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "fetch_data",
        "description": (
            "Retrieve the actual values for a given data key as a structured object. "
            "Use this to inspect data you intend to place, so commentary reflects "
            "actual values. Read-only — does NOT modify the deck. Inspect, do not "
            "transcribe: exact figures are rendered from the data layer, not your text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data_key": {"type": "string"},
                "window": {
                    "type": "string",
                    "description": "Optional period window, e.g. 'last_24m', 'YTD'. Defaults to source default.",
                },
            },
            "required": ["data_key"],
        },
    },
    {
        "name": "load_skill",
        "description": (
            "Load the full content of a skill by name. Call this when the skill "
            "catalog in the system prompt indicates a skill is relevant to your "
            "current step. Skills stay loaded for the rest of the session — do not "
            "reload a skill you have already loaded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "enum": ["pptx-spec", "corporate-style", "data-viz"],
                }
            },
            "required": ["skill_name"],
        },
    },
    {
        "name": "validate_spec",
        "description": (
            "Validate a deck spec against the schema and the renderer's supported "
            "style tokens, layouts, and element types. Returns ok=true, or a list of "
            "structured errors (each with path, problem, and fix). ALWAYS call this "
            "before render_deck and fix any errors first. Does not produce a file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "The full deck spec JSON."}
            },
            "required": ["spec"],
        },
    },
    {
        "name": "render_deck",
        "description": (
            "Render a validated deck spec into a .pptx using the audited renderer. "
            "Only call after validate_spec returns ok=true. Returns the output path. "
            "This is the terminal action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object"},
                "output_name": {
                    "type": "string",
                    "description": "Base filename without extension.",
                },
            },
            "required": ["spec", "output_name"],
        },
    },
]
