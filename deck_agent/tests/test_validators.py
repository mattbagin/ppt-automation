"""
Unit tests for the layered spec validator — the safety-critical component.

Organization mirrors validators.py: one test class per layer, plus regression
tests for the "false ok" bugs these layers exist to prevent, happy-path tests,
and error-quality checks (every error must carry a populated path / problem /
fix, because those fields drive the model's self-correction).

The data catalog is defined locally (not imported from tools.data) so tests
exercise the validator contract, not the mock manifest.
"""

from __future__ import annotations

import pytest

from deck_agent.renderer_capabilities import (
    ALL_STYLE_TOKENS,
    ELEMENT_TYPES,
    LAYOUT_NAMES,
    LAYOUTS,
)
from deck_agent.validation import validate_spec
from deck_agent.validation.result import ValidationError, ValidationResult

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

CATALOG: dict[str, dict] = {
    "small_table": {"shape": "table", "row_count": 6},
    "big_table": {"shape": "table", "row_count": 40},
    "ts_series": {"shape": "series", "period_count": 24},
    "one_scalar": {"shape": "scalar"},
    "grid_matrix": {"shape": "matrix", "row_count": 4},
}


def slide(layout: str, *elements: dict) -> dict:
    return {"layout": layout, "elements": list(elements)}


def spec_of(*slides: dict) -> dict:
    return {"slides": list(slides)}


def errors_at(result: ValidationResult, path_fragment: str) -> list[ValidationError]:
    return [e for e in result.errors if path_fragment in e.path]


def assert_single_error(result: ValidationResult, path_fragment: str) -> ValidationError:
    assert not result.ok
    matching = errors_at(result, path_fragment)
    assert len(result.errors) == 1, (
        f"expected exactly one error, got: {[(e.path, e.problem) for e in result.errors]}"
    )
    assert matching, (
        f"no error at path containing '{path_fragment}'; "
        f"got paths: {[e.path for e in result.errors]}"
    )
    return matching[0]


TITLE = {"type": "title", "text": "A Title"}
GOOD_TABLE = {"type": "table", "data_key": "small_table", "style": "risk_standard"}
GOOD_CHART = {"type": "chart", "data_key": "ts_series", "style": "corporate_ts"}
GOOD_TEXT = {"type": "text", "text": "Draft commentary.", "style": "body"}
GOOD_KPI = {"type": "kpi", "data_key": "one_scalar"}


# ---------------------------------------------------------------------------
# Layer 1 — schema / structural
# ---------------------------------------------------------------------------

class TestLayer1Schema:
    @pytest.mark.parametrize("bad_spec", ["not a dict", 42, None, ["slides"]])
    def test_non_dict_spec_rejected(self, bad_spec):
        result = validate_spec(bad_spec, CATALOG)
        assert not result.ok
        assert result.errors[0].path == "<root>"

    def test_missing_slides_rejected(self):
        result = validate_spec({}, CATALOG)
        assert_single_error(result, "<root>.slides")

    @pytest.mark.parametrize("slides", [[], "not a list", {"a": 1}])
    def test_slides_must_be_nonempty_array(self, slides):
        result = validate_spec({"slides": slides}, CATALOG)
        assert_single_error(result, "<root>.slides")

    def test_non_dict_slide_rejected(self):
        result = validate_spec({"slides": ["not a slide"]}, CATALOG)
        assert_single_error(result, "slides[0]")

    def test_slide_missing_layout_rejected(self):
        result = validate_spec({"slides": [{"elements": [dict(TITLE)]}]}, CATALOG)
        assert_single_error(result, "slides[0].layout")

    @pytest.mark.parametrize("elements", [None, "not a list"])
    def test_slide_missing_or_non_list_elements_rejected(self, elements):
        bad = {"layout": "commentary"}
        if elements is not None:
            bad["elements"] = elements
        result = validate_spec({"slides": [bad]}, CATALOG)
        assert_single_error(result, "slides[0].elements")

    def test_non_dict_element_rejected(self):
        result = validate_spec(spec_of(slide("commentary", "not an element")), CATALOG)
        assert_single_error(result, "slides[0].elements[0]")

    def test_element_missing_type_rejected(self):
        result = validate_spec(spec_of(slide("commentary", {"text": "hi"})), CATALOG)
        assert_single_error(result, "slides[0].elements[0].type")

    def test_structural_errors_collected_across_slides(self):
        """Fail-RICH within the layer: both bad slides reported in one pass."""
        result = validate_spec(
            {"slides": [{"elements": []}, {"layout": "commentary"}]}, CATALOG
        )
        assert not result.ok
        assert errors_at(result, "slides[0].layout")
        assert errors_at(result, "slides[1].elements")

    def test_fail_fast_between_layers(self):
        """A structural error suppresses vocabulary noise: the bogus layout on
        the same slide is NOT also reported."""
        result = validate_spec(
            spec_of({"layout": "no_such_layout", "elements": [{"text": "no type"}]}),
            CATALOG,
        )
        assert not result.ok
        assert errors_at(result, "elements[0].type")
        assert not errors_at(result, "slides[0].layout")


# ---------------------------------------------------------------------------
# Layer 2 — closed vocabulary
# ---------------------------------------------------------------------------

class TestLayer2Vocabulary:
    def test_unknown_layout_rejected_with_valid_alternatives(self):
        result = validate_spec(spec_of(slide("freestyle", dict(TITLE))), CATALOG)
        err = assert_single_error(result, "slides[0].layout")
        for name in LAYOUT_NAMES:
            assert name in err.fix_hint

    def test_unknown_element_type_rejected_with_valid_alternatives(self):
        result = validate_spec(
            spec_of(slide("commentary", {"type": "hologram"})), CATALOG
        )
        err = assert_single_error(result, "elements[0].type")
        for etype in ELEMENT_TYPES:
            assert etype in err.fix_hint

    def test_invented_style_token_rejected(self):
        el = {"type": "text", "text": "x", "style": "my_cool_style"}
        result = validate_spec(spec_of(slide("commentary", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, "elements[1].style")
        assert "my_cool_style" in err.problem

    def test_chart_style_on_table_rejected(self):
        """Regression: a real token from the WRONG family used to pass."""
        el = {"type": "table", "data_key": "small_table", "style": "corporate_ts"}
        result = validate_spec(spec_of(slide("single_table", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, "elements[1].style")
        assert "corporate_ts" in err.problem
        assert "risk_standard" in err.fix_hint  # points at the right family

    def test_table_style_on_chart_rejected(self):
        el = {"type": "chart", "data_key": "ts_series", "style": "risk_compact"}
        result = validate_spec(spec_of(slide("two_charts", dict(TITLE), el)), CATALOG)
        assert_single_error(result, "elements[1].style")

    def test_any_style_on_title_rejected(self):
        el = {"type": "title", "text": "T", "style": "body"}
        result = validate_spec(spec_of(slide("commentary", el)), CATALOG)
        err = assert_single_error(result, "elements[0].style")
        assert "remove" in err.fix_hint.lower()

    def test_correct_family_styles_pass(self):
        result = validate_spec(
            spec_of(slide("table_and_chart", dict(TITLE), dict(GOOD_TABLE),
                          dict(GOOD_CHART), dict(GOOD_TEXT))),
            CATALOG,
        )
        assert result.ok

    def test_style_family_not_checked_for_unknown_element_type(self):
        """An unknown element type reports ONE error (the type), not a second
        noise error about its style's family."""
        el = {"type": "hologram", "style": "body"}
        result = validate_spec(spec_of(slide("commentary", dict(TITLE), el)), CATALOG)
        assert_single_error(result, "elements[1].type")


# ---------------------------------------------------------------------------
# Layer 3 — referential integrity
# ---------------------------------------------------------------------------

class TestLayer3Referential:
    def test_unknown_data_key_rejected(self):
        el = {"type": "table", "data_key": "no_such_key", "style": "risk_standard"}
        result = validate_spec(spec_of(slide("single_table", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, "elements[1].data_key")
        assert "no_such_key" in err.problem

    def test_unknown_data_key_fix_hint_suggests_real_keys(self):
        el = {"type": "table", "data_key": "small_tabel", "style": "risk_standard"}
        result = validate_spec(spec_of(slide("single_table", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, "elements[1].data_key")
        assert any(key in err.fix_hint for key in CATALOG)

    def test_known_data_key_passes(self):
        result = validate_spec(
            spec_of(slide("single_table", dict(TITLE), dict(GOOD_TABLE))), CATALOG
        )
        assert result.ok


# ---------------------------------------------------------------------------
# Layer 4 — renderability
# ---------------------------------------------------------------------------

class TestElementLayoutFit:
    """Regression tests for the two 'false ok' bugs: elements placed on layouts
    with no region for them used to validate cleanly."""

    @pytest.mark.parametrize("layout", ["two_charts", "title_slide", "commentary"])
    def test_table_on_tableless_layout_rejected(self, layout):
        result = validate_spec(spec_of(slide(layout, dict(GOOD_TABLE))), CATALOG)
        err = assert_single_error(result, "elements[0].type")
        assert "table" in err.problem
        assert "single_table" in err.fix_hint  # suggests a layout that works

    @pytest.mark.parametrize("layout", ["commentary", "single_table", "title_slide"])
    def test_chart_on_chartless_layout_rejected(self, layout):
        result = validate_spec(spec_of(slide(layout, dict(GOOD_CHART))), CATALOG)
        err = assert_single_error(result, "elements[0].type")
        assert "chart" in err.problem

    def test_kpi_only_on_supporting_layouts(self):
        ok = validate_spec(
            spec_of(slide("commentary", dict(TITLE), dict(GOOD_KPI))), CATALOG
        )
        assert ok.ok
        bad = validate_spec(spec_of(slide("two_charts", dict(GOOD_KPI))), CATALOG)
        assert_single_error(bad, "elements[0].type")

    def test_misplaced_element_reports_exactly_one_error(self):
        """No cascade: an oversized table on a tableless layout is reported as
        misplacement only, not misplacement + capacity."""
        el = {"type": "table", "data_key": "big_table", "style": "risk_standard"}
        result = validate_spec(spec_of(slide("commentary", dict(TITLE), el)), CATALOG)
        assert len(result.errors) == 1

    def test_layout_fit_skipped_for_unknown_layout(self):
        """Unknown layout is the vocabulary layer's error; layer 4 stays quiet."""
        result = validate_spec(
            spec_of(slide("no_such_layout", dict(GOOD_TABLE))), CATALOG
        )
        assert_single_error(result, "slides[0].layout")


class TestDataShapeFit:
    @pytest.mark.parametrize(
        "etype,style,data_key",
        [
            ("chart", "corporate_ts", "one_scalar"),   # chart wants series/matrix
            ("chart", "corporate_ts", "small_table"),  # chart can't take a table
            ("kpi", None, "small_table"),              # kpi wants a scalar
            ("kpi", None, "ts_series"),
            ("table", "risk_standard", "ts_series"),   # table wants table/matrix
            ("table", "risk_standard", "one_scalar"),
        ],
    )
    def test_shape_mismatch_rejected(self, etype, style, data_key):
        el = {"type": etype, "data_key": data_key}
        if style:
            el["style"] = style
        result = validate_spec(
            spec_of(slide("table_and_chart", dict(TITLE), el)), CATALOG
        )
        err = assert_single_error(result, "elements[1].data_key")
        assert CATALOG[data_key]["shape"] in err.problem

    @pytest.mark.parametrize(
        "etype,style,data_key",
        [
            ("chart", "corporate_bar", "grid_matrix"),  # matrix ok for both
            ("table", "risk_compact", "grid_matrix"),
            ("kpi", None, "one_scalar"),
        ],
    )
    def test_matching_shapes_pass(self, etype, style, data_key):
        el = {"type": etype, "data_key": data_key}
        if style:
            el["style"] = style
        result = validate_spec(
            spec_of(slide("table_and_chart", dict(TITLE), el)), CATALOG
        )
        assert result.ok, [(e.path, e.problem) for e in result.errors]


class TestDataKeyOnNonDataElements:
    """Regression: a data_key on title/text was silently ignored — the model
    could believe a figure would be rendered that never appears."""

    @pytest.mark.parametrize("etype", ["title", "text"])
    def test_data_key_on_non_data_element_rejected(self, etype):
        el = {"type": etype, "text": "x", "data_key": "one_scalar"}
        if etype == "text":
            el["style"] = "body"
        result = validate_spec(spec_of(slide("commentary", el)), CATALOG)
        err = assert_single_error(result, "elements[0].data_key")
        assert "ignored" in err.problem

    def test_rejected_even_when_data_key_is_valid(self):
        """The key existing in the catalog does not make it renderable here."""
        el = {"type": "text", "text": "x", "style": "body", "data_key": "small_table"}
        result = validate_spec(spec_of(slide("commentary", dict(TITLE), el)), CATALOG)
        assert_single_error(result, "elements[1].data_key")


class TestCapacity:
    def test_table_over_row_limit_rejected(self):
        el = {"type": "table", "data_key": "big_table", "style": "risk_standard"}
        result = validate_spec(spec_of(slide("single_table", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, "elements[1].data_key")
        assert "40" in err.problem   # actual rows
        assert "18" in err.problem   # layout limit
        assert "18" in err.fix_hint  # actionable target

    def test_table_within_row_limit_passes(self):
        result = validate_spec(
            spec_of(slide("single_table", dict(TITLE), dict(GOOD_TABLE))), CATALOG
        )
        assert result.ok

    def test_row_limit_differs_by_layout(self):
        """big_table (40 rows) fails everywhere, but the reported limit must be
        the layout's own."""
        el = {"type": "table", "data_key": "big_table", "style": "risk_standard"}
        result = validate_spec(
            spec_of(slide("table_and_chart", dict(TITLE), el)), CATALOG
        )
        err = assert_single_error(result, "elements[1].data_key")
        assert "12" in err.problem

    def test_capabilities_drift_backstop(self, monkeypatch):
        """If the capabilities file ever claims a layout allows tables but gives
        it zero row capacity, validation must ERROR, not silently pass — this is
        the regression test for the falsy `max_rows and` bug."""
        drifted = dict(LAYOUTS["commentary"])
        drifted["allowed_element_types"] = {"title", "text", "kpi", "table"}
        drifted["table_max_rows"] = 0
        monkeypatch.setitem(LAYOUTS, "commentary", drifted)

        result = validate_spec(
            spec_of(slide("commentary", dict(TITLE), dict(GOOD_TABLE))), CATALOG
        )
        err = assert_single_error(result, "elements[1].data_key")
        assert "0" in err.problem


class TestSlotFit:
    def test_too_many_elements_for_layout_rejected(self):
        result = validate_spec(
            spec_of(slide("commentary", dict(TITLE), dict(GOOD_TEXT),
                          {"type": "text", "text": "extra", "style": "body"})),
            CATALOG,
        )
        err = assert_single_error(result, "slides[0].elements")
        assert "3" in err.problem  # elements defined
        assert "2" in err.problem  # slots available

    def test_element_count_at_slot_limit_passes(self):
        result = validate_spec(
            spec_of(slide("commentary", dict(TITLE), dict(GOOD_TEXT))), CATALOG
        )
        assert result.ok


# ---------------------------------------------------------------------------
# Happy path + result serialization
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_representative_deck_validates(self):
        """A realistic multi-slide deck exercising every element type."""
        result = validate_spec(
            spec_of(
                slide("title_slide", dict(TITLE),
                      {"type": "text", "text": "Monthly IRRBB", "style": "body"}),
                slide("section_header", dict(TITLE)),
                slide("table_and_chart", dict(TITLE), dict(GOOD_TABLE),
                      dict(GOOD_CHART), dict(GOOD_TEXT)),
                slide("two_charts", dict(TITLE), dict(GOOD_CHART),
                      {"type": "chart", "data_key": "grid_matrix",
                       "style": "corporate_bar"}),
                slide("commentary", dict(TITLE), dict(GOOD_KPI)),
            ),
            CATALOG,
        )
        assert result.ok, [(e.path, e.problem) for e in result.errors]
        assert result.errors == []

    def test_ok_serializes_minimal(self):
        result = validate_spec(
            spec_of(slide("section_header", dict(TITLE))), CATALOG
        )
        assert result.to_tool_result() == {"ok": True}


class TestErrorQuality:
    """Every error must carry populated path / problem / fix — those three
    fields are what drive the model's self-correction next turn."""

    KITCHEN_SINK = spec_of(
        slide("no_such_layout", dict(TITLE)),
        slide("two_charts",
              {"type": "table", "data_key": "big_table", "style": "corporate_ts"},
              {"type": "chart", "data_key": "missing_key", "style": "corporate_ts"},
              {"type": "text", "text": "x", "style": "body",
               "data_key": "one_scalar"},
              {"type": "kpi", "data_key": "small_table"}),
    )

    def test_every_error_fully_populated(self):
        result = validate_spec(self.KITCHEN_SINK, CATALOG)
        assert not result.ok
        assert len(result.errors) >= 4
        for err in result.errors:
            assert err.path.startswith("slides["), err
            assert err.problem.strip(), err
            assert err.fix_hint.strip(), err

    def test_tool_result_shape(self):
        payload = validate_spec(self.KITCHEN_SINK, CATALOG).to_tool_result()
        assert payload["ok"] is False
        assert payload["error_count"] == len(payload["errors"])
        for err in payload["errors"]:
            assert set(err) == {"path", "problem", "fix"}

    def test_style_fix_hints_reference_real_tokens(self):
        """Wrong-family style errors must point at tokens that actually exist."""
        el = {"type": "table", "data_key": "small_table", "style": "corporate_ts"}
        result = validate_spec(spec_of(slide("single_table", dict(TITLE), el)), CATALOG)
        err = assert_single_error(result, ".style")
        assert any(tok in err.fix_hint for tok in ALL_STYLE_TOKENS)
