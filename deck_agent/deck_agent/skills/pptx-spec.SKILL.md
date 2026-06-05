# pptx-spec skill (PLACEHOLDER)

> Replace this with your real spec schema (handled in your other thread).

This skill defines the deck spec structure the agent must conform to: valid
element types, layouts, and how to compose slides.

## Spec shape (illustrative — align with your frozen schema)

```json
{
  "slides": [
    {
      "layout": "table_and_chart",
      "elements": [
        {"type": "title", "text": "NII Sensitivity"},
        {"type": "table", "data_key": "nii_sensitivity", "style": "risk_standard"},
        {"type": "chart", "data_key": "nii_ts", "style": "corporate_ts"},
        {"type": "text", "text": "Draft commentary...", "style": "body"}
      ]
    }
  ]
}
```

## Element types
- `title` — slide title text (no data_key)
- `text`  — body / callout / footnote text (no data_key)
- `table` — tabular data (data_key with shape table|matrix)
- `chart` — visualization (data_key with shape series|matrix); see data-viz skill
- `kpi`   — single highlighted value (data_key with shape scalar)

## Layouts and slot counts
See the renderer's capabilities; do not exceed a layout's element slots.
