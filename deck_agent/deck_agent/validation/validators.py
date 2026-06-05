"""
The validation layers behind validate_spec.

Ordering principle: cheap-and-structural first, expensive-and-semantic last.
Fail-RICH within a layer (collect all errors so the model can fix them in one
revision). Fail-FAST only between layers where a later layer would be meaningless
(e.g. don't check vocabulary on a spec that doesn't parse).

Layer 1 — schema/structural : is it well-formed?
Layer 2 — vocabulary        : do these tokens / layouts / element types exist?
Layer 3 — referential       : do referenced data_keys / chart configs exist?
Layer 4 — renderability      : given valid structure + real metadata, will it
                               actually render correctly? (shape-fit, capacity,
                               layout-slot conflict)

NOTE: chart-TYPE compatibility checking has been intentionally retired. The
data-viz skill now owns visualization decisioning and produces chart configs,
so "is this the right chart for this data" is answered upstream by the component
that knows the rules — it doesn't need re-validating here.
"""

from __future__ import annotations

from ..renderer_capabilities import (
    ALL_STYLE_TOKENS,
    ELEMENT_DATA_SHAPES,
    ELEMENT_TYPES,
    LAYOUT_NAMES,
    layout_limits,
)
from .result import ValidationError, ValidationResult


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_spec(spec: dict, data_catalog: dict) -> ValidationResult:
    """Validate a deck spec in layers.

    data_catalog: metadata about each data_key (shape, row_count, period_count,
    units, ...) — the SAME metadata get_available_data exposes. We validate
    against METADATA, not full data payloads, to keep this cheap.
    """
    errors: list[ValidationError] = []

    # Layer 1 — structural. If the spec is malformed, deeper checks are noise.
    errors.extend(_validate_schema(spec))
    if errors:
        return ValidationResult(ok=False, errors=errors)

    # Layer 2 — closed vocabulary.
    errors.extend(_validate_vocabulary(spec))

    # Layer 3 — referential integrity.
    errors.extend(_validate_data_references(spec, data_catalog))

    # Layer 4 — renderability (shape-fit, capacity, layout-slot conflict).
    errors.extend(_validate_renderability(spec, data_catalog))

    return ValidationResult(ok=not errors, errors=errors)


# ---------------------------------------------------------------------------
# Layer 1 — schema / structural
# ---------------------------------------------------------------------------

def _validate_schema(spec: dict) -> list[ValidationError]:
    """Minimal structural checks. Replace/extend with your frozen schema
    (jsonschema, pydantic, etc.) from your schema thread."""
    errors: list[ValidationError] = []

    if not isinstance(spec, dict):
        return [ValidationError("<root>", "Spec must be a JSON object.",
                                "Return an object with a top-level 'slides' array.")]

    slides = spec.get("slides")
    if slides is None:
        errors.append(ValidationError(
            "<root>.slides", "Spec is missing the 'slides' array.",
            "Add a 'slides' array; each item is a slide object with 'layout' and 'elements'.",
        ))
        return errors

    if not isinstance(slides, list) or not slides:
        errors.append(ValidationError(
            "<root>.slides", "'slides' must be a non-empty array.",
            "Provide at least one slide object in 'slides'.",
        ))
        return errors

    for s_idx, slide in enumerate(slides):
        path = f"slides[{s_idx}]"
        if not isinstance(slide, dict):
            errors.append(ValidationError(path, "Slide must be an object.",
                                          "Each slide is an object with 'layout' and 'elements'."))
            continue
        if "layout" not in slide:
            errors.append(ValidationError(f"{path}.layout", "Slide is missing 'layout'.",
                                          f"Add a 'layout'; valid layouts: {sorted(LAYOUT_NAMES)}."))
        elements = slide.get("elements")
        if elements is None or not isinstance(elements, list):
            errors.append(ValidationError(f"{path}.elements", "Slide is missing an 'elements' array.",
                                          "Add an 'elements' array (may be empty for some layouts)."))
            continue
        for e_idx, element in enumerate(elements):
            epath = f"{path}.elements[{e_idx}]"
            if not isinstance(element, dict):
                errors.append(ValidationError(epath, "Element must be an object.",
                                              "Each element is an object with at least a 'type'."))
            elif "type" not in element:
                errors.append(ValidationError(f"{epath}.type", "Element is missing 'type'.",
                                              f"Add a 'type'; valid types: {sorted(ELEMENT_TYPES)}."))
    return errors


# ---------------------------------------------------------------------------
# Layer 2 — closed vocabulary
# ---------------------------------------------------------------------------

def _validate_vocabulary(spec: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for s_idx, slide in enumerate(spec["slides"]):
        path = f"slides[{s_idx}]"

        layout = slide.get("layout")
        if layout is not None and layout not in LAYOUT_NAMES:
            errors.append(ValidationError(
                f"{path}.layout",
                f"Layout '{layout}' is not supported.",
                f"Valid layouts are: {sorted(LAYOUT_NAMES)}.",
            ))

        for e_idx, element in enumerate(slide.get("elements", [])):
            epath = f"{path}.elements[{e_idx}]"
            etype = element.get("type")
            if etype is not None and etype not in ELEMENT_TYPES:
                errors.append(ValidationError(
                    f"{epath}.type",
                    f"Element type '{etype}' is not supported.",
                    f"Valid element types are: {sorted(ELEMENT_TYPES)}.",
                ))

            style = element.get("style")
            if style is not None and style not in ALL_STYLE_TOKENS:
                errors.append(ValidationError(
                    f"{epath}.style",
                    f"Style token '{style}' is not supported.",
                    f"Valid style tokens are: {sorted(ALL_STYLE_TOKENS)}. "
                    f"Never invent a token — if you need one that doesn't exist, "
                    f"flag it to the user.",
                ))
    return errors


# ---------------------------------------------------------------------------
# Layer 3 — referential integrity
# ---------------------------------------------------------------------------

def _validate_data_references(spec: dict, data_catalog: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for s_idx, slide in enumerate(spec["slides"]):
        for e_idx, element in enumerate(slide.get("elements", [])):
            epath = f"slides[{s_idx}].elements[{e_idx}]"
            data_key = element.get("data_key")
            if data_key is None:
                continue  # title/text/etc. carry no data reference
            if data_key not in data_catalog:
                errors.append(ValidationError(
                    f"{epath}.data_key",
                    f"data_key '{data_key}' does not exist in the data layer.",
                    f"Available keys: {_nearby_keys(data_key, data_catalog)}. "
                    f"If the value you need is not available, flag it to the user "
                    f"rather than substituting another key.",
                ))
    return errors


def _nearby_keys(missing: str, data_catalog: dict, limit: int = 8) -> list[str]:
    """Surface plausibly-related keys to help the model self-correct.
    Cheap prefix/substring match; swap for difflib if you want fuzzier hints."""
    stem = missing.split("_")[0] if "_" in missing else missing[:4]
    related = [k for k in data_catalog if stem and stem.lower() in k.lower()]
    return sorted(related)[:limit] or sorted(data_catalog)[:limit]


# ---------------------------------------------------------------------------
# Layer 4 — renderability
# ---------------------------------------------------------------------------

def _validate_renderability(spec: dict, data_catalog: dict) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for s_idx, slide in enumerate(spec["slides"]):
        path = f"slides[{s_idx}]"

        # Slide-level: too many elements for the layout's slots.
        errors.extend(_check_slide_layout_fit(slide, path))

        for e_idx, element in enumerate(slide.get("elements", [])):
            epath = f"{path}.elements[{e_idx}]"
            errors.extend(_check_element_data_fit(element, data_catalog, epath))
            errors.extend(_check_capacity(element, slide, data_catalog, epath))
    return errors


def _check_element_data_fit(element, data_catalog, path) -> list[ValidationError]:
    """Element type must match the SHAPE of the data it points at."""
    errors: list[ValidationError] = []
    etype = element.get("type")
    data_key = element.get("data_key")
    if data_key is None:
        return errors

    meta = data_catalog.get(data_key)
    if meta is None:
        return errors  # referential layer already reported the missing key

    shape = meta.get("shape")
    allowed = ELEMENT_DATA_SHAPES.get(etype, set())
    if allowed and shape not in allowed:
        errors.append(ValidationError(
            f"{path}.data_key",
            f"Element type '{etype}' expects data shaped as {sorted(allowed)}, "
            f"but '{data_key}' is a '{shape}'.",
            f"'{data_key}' is a '{shape}'. {_suggest_element_for_shape(shape)}",
        ))
    return errors


def _suggest_element_for_shape(shape: str) -> str:
    return {
        "scalar": "Use a 'kpi' element for a single value.",
        "series": "Use a 'chart' element for a time series.",
        "table":  "Use a 'table' element for tabular data.",
        "matrix": "Use a 'table' or 'chart' element for matrix data.",
    }.get(shape, "Choose an element type matching this data shape.")


def _check_capacity(element, slide, data_catalog, path) -> list[ValidationError]:
    """Predictable overflow: a table with more rows than the layout region holds."""
    errors: list[ValidationError] = []
    if element.get("type") != "table":
        return errors

    data_key = element.get("data_key")
    meta = data_catalog.get(data_key) if data_key else None
    if meta is None:
        return errors

    rows = meta.get("row_count", 0)
    limits = layout_limits(slide.get("layout", ""))
    max_rows = limits.get("table_max_rows", 0)
    if max_rows and rows > max_rows:
        errors.append(ValidationError(
            f"{path}.data_key",
            f"Table has {rows} rows; layout '{slide.get('layout')}' holds {max_rows}.",
            f"Filter to the top {max_rows} rows, split across two slides, or "
            f"choose a layout with a larger table region.",
        ))
    return errors


def _check_slide_layout_fit(slide, path) -> list[ValidationError]:
    """Slide claims more elements than its layout has slots."""
    errors: list[ValidationError] = []
    layout = slide.get("layout")
    limits = layout_limits(layout) if layout else {}
    slots = limits.get("element_slots")
    if slots is None:
        return errors  # unknown layout already reported by vocabulary layer

    n_elements = len(slide.get("elements", []))
    if n_elements > slots:
        errors.append(ValidationError(
            f"{path}.elements",
            f"Layout '{layout}' has {slots} element slots but the slide defines "
            f"{n_elements} elements.",
            f"Remove {n_elements - slots} element(s), or choose a layout with more "
            f"slots. Layouts and their slot counts are in the pptx-spec skill.",
        ))
    return errors
