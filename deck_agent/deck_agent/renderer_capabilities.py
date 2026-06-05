"""
SINGLE SOURCE OF TRUTH for renderer capabilities.

Both the validator (validation/validators.py) and the renderer
(tools/deck.py::render_deck_impl) import from here. This is the most important
coupling in the system: if the validator believes a table holds 15 rows and the
renderer holds 12, a spec can validate and then overflow at render time, producing
a broken slide with no error for the model to learn from (a false "ok").

Never duplicate these values anywhere else. Edit them HERE only.

# TODO: replace the example tokens/limits below with your real corporate values.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Style tokens (closed vocabulary). The model may ONLY use tokens listed here.
# These should mirror what corporate-style.SKILL.md documents to the model.
# ---------------------------------------------------------------------------

CHART_STYLE_TOKENS: set[str] = {
    "corporate_ts",         # time-series line style
    "corporate_bar",        # categorical bar style
    "corporate_waterfall",  # waterfall / bridge style
}

TABLE_STYLE_TOKENS: set[str] = {
    "risk_standard",        # default risk-report table style
    "risk_compact",         # tighter style for dense tables
}

TEXT_STYLE_TOKENS: set[str] = {
    "body",
    "callout",
    "footnote",
}

ALL_STYLE_TOKENS: set[str] = (
    CHART_STYLE_TOKENS | TABLE_STYLE_TOKENS | TEXT_STYLE_TOKENS
)

# ---------------------------------------------------------------------------
# Element types the spec / renderer support.
# ---------------------------------------------------------------------------

ELEMENT_TYPES: set[str] = {"title", "text", "table", "chart", "kpi"}

# Which data shapes each element type can accept.
# Used by the renderability layer (shape-fit check).
ELEMENT_DATA_SHAPES: dict[str, set[str]] = {
    "table": {"table", "matrix"},
    "chart": {"series", "matrix"},
    "kpi":   {"scalar"},
    # title / text carry no data_key -> not listed (None handled in validator)
}

# ---------------------------------------------------------------------------
# Layouts and their capacity. Slot counts and region dimensions live together
# so the validator can check fit and the renderer can place elements.
# Dimensions are in EMU-agnostic "points" here for illustration; convert to your
# renderer's unit (python-pptx uses EMU via Inches()/Pt()).
# ---------------------------------------------------------------------------

LAYOUTS: dict[str, dict] = {
    "title_slide": {
        "element_slots": 2,            # title + subtitle
        "table_max_rows": 0,
    },
    "section_header": {
        "element_slots": 1,
        "table_max_rows": 0,
    },
    "single_table": {
        "element_slots": 2,            # title + one table
        "table_max_rows": 18,
        "chart_region": None,
    },
    "table_and_chart": {
        "element_slots": 4,            # title + table + chart + commentary
        "table_max_rows": 12,
        "chart_region": {"width_pt": 360, "height_pt": 280},
    },
    "two_charts": {
        "element_slots": 3,            # title + two charts
        "table_max_rows": 0,
        "chart_region": {"width_pt": 300, "height_pt": 240},
    },
    "commentary": {
        "element_slots": 2,            # title + body text
        "table_max_rows": 0,
    },
}

LAYOUT_NAMES: set[str] = set(LAYOUTS.keys())


def layout_limits(layout_name: str) -> dict:
    """Return the capacity dict for a layout, or an empty dict if unknown.

    Callers should have already validated the layout name exists (vocabulary
    layer); this is defensive.
    """
    return LAYOUTS.get(layout_name, {})
