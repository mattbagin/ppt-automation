"""
Data-layer tools: get_available_data and fetch_data.

STUB IMPLEMENTATIONS. These return mock data so the loop runs end-to-end.
Wire them to your real sources:
  - Bloomberg via blpapi (you already run blpapi pulls on a schedule)
  - internal risk DB
  - Excel source files (pandas / openpyxl)

Recommended pattern (from the design discussion): an extraction layer normalizes
ALL sources into a single structured "data manifest" with metadata, and these
tools read from that manifest. That keeps the generation path simple, testable,
and auditable — reviewers can see exactly what data drove a given deck.

The METADATA shape returned by get_available_data is what the validator's
renderability layer checks against. Keep these two in agreement:
  shape         : one of "scalar" | "series" | "table" | "matrix"
  row_count     : for tables — used by the capacity check
  period_count  : for series — informational
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Mock manifest. Replace _MANIFEST with your real extraction-layer output.
# ---------------------------------------------------------------------------

_MANIFEST: dict[str, dict] = {
    "nii_sensitivity": {
        "description": "NII sensitivity to parallel rate shocks (current period).",
        "units": "CAD millions",
        "shape": "table",
        "row_count": 6,
        "values": [  # only returned by fetch_data
            ["Shock", "NII Impact"],
            ["+200bps", "142.3"],
            ["+100bps", "71.8"],
            ["-100bps", "-69.4"],
            ["-200bps", "-141.1"],
            ["Base", "0.0"],
        ],
    },
    "nii_ts": {
        "description": "12-month NII time series.",
        "units": "CAD millions",
        "shape": "series",
        "period_count": 24,
        "values": {"2024-06": 1180.2, "2024-07": 1192.5},  # truncated mock
    },
    "eve_shock_100bps": {
        "description": "EVE impact under +100bps parallel shock.",
        "units": "CAD millions",
        "shape": "scalar",
        "values": -312.6,
    },
    "report_date": {
        "description": "As-of date for this reporting cycle.",
        "units": "date",
        "shape": "scalar",
        "values": "2026-05-31",
    },
}


def get_available_data_impl(topic_filter: str | None = None) -> dict:
    """Return catalog metadata (NOT values). Cheap; safe to call freely."""
    catalog = {}
    for key, meta in _MANIFEST.items():
        if topic_filter and topic_filter.lower() not in (
            key + " " + meta.get("description", "")
        ).lower():
            continue
        catalog[key] = {
            k: v for k, v in meta.items() if k != "values"
        }
    return {"data_keys": catalog}


def fetch_data_impl(data_key: str, window: str | None = None) -> dict:
    """Return actual values for a key. Read-only."""
    if data_key not in _MANIFEST:
        raise KeyError(f"Unknown data_key: {data_key}")
    meta = _MANIFEST[data_key]
    return {
        "data_key": data_key,
        "shape": meta["shape"],
        "units": meta.get("units"),
        "window": window,
        "values": meta.get("values"),
    }


def get_data_catalog() -> dict:
    """Internal helper: the metadata-only catalog the validator needs.

    Used by validate_spec so renderability checks can see data shapes/row counts
    without pulling full payloads.
    """
    return {
        key: {k: v for k, v in meta.items() if k != "values"}
        for key, meta in _MANIFEST.items()
    }
