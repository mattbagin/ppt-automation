# data-viz skill (PLACEHOLDER)

> Replace with your real visualization decisioning rules.

Owns visualization decisioning AND chart config production. "Is this the right
chart for this data" is answered HERE, so it is not re-validated downstream.

## Chart-type selection (illustrative)
- Time series (shape: series, >= 2 periods) -> line, style `corporate_ts`
- Categorical comparison (non-compositional) -> bar, style `corporate_bar`
- Sequential contributions / bridge          -> waterfall, style `corporate_waterfall`
- Single value (shape: scalar)               -> not a chart; use a `kpi` element

## Output: chart config (declarative, NOT code)
Produce a declarative chart config the audited charting function consumes — keep
charts inside the "model decides structure, audited code renders" discipline.
Do NOT emit executable charting code by default.

```json
{"type": "chart", "data_key": "nii_ts", "chart_type": "line", "style": "corporate_ts"}
```
