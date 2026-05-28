# Macro Analysis Multimodal Capabilities

## Target Component
`src/agents/macro_analyst_agent.py`

## Architecture Context
Macro-economic analysis heavily relies on charts, yield curves, dot plots from the Federal Reserve, and global supply chain heatmaps. Most of this data is published natively as images (PNGs/PDFs) rather than tabular data. Currently, our system struggles to ingest visual macroeconomic indicators.

## Approaches

### Approach 1: Text-only Extraction Pipeline
Use traditional OCR (Optical Character Recognition) via a Python library to strip text from Fed releases and pass it to the `macro_analyst_agent`.
- **Pros**: Keeps the architecture entirely text-based, saving on multimodal token costs.
- **Cons**: OCR loses spatial context (e.g., the shape of a yield curve), which is where the actual macroeconomic signal resides.

### Approach 2: Hermes Vision API for Chart Parsing
Leverage Hermes' built-in vision capabilities. The system can screenshot live macroeconomic dashboards or feed PDF charts directly into Hermes. The vision model analyzes the visual structure (e.g., "The 2-year and 10-year yield curve has inverted significantly in the last hour") and outputs a quantitative summary payload.
- **Pros**: Captures the full spatial context of charts; handles complex visualizations seamlessly.
- **Cons**: Vision models can be more expensive and slightly slower than text models.

## Recommendation: Approach 2 (Hermes Vision API)
Macro trading is inherently visual. Being able to natively interpret a Federal Reserve dot plot or an inflation heatmap without relying on a third-party tabular data provider provides a massive advantage. Hermes' vision capabilities perfectly bridge this gap.
