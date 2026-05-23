# Data Ingestion Pipelines

## Real-Time Market Data
The trading system relies heavily on low-latency, accurate market data to feed the analytical sub-agents.
- **WebSockets vs REST**: Utilizing WebSockets via Alpaca for real-time order book depth, OHLCV aggregates, and tick-level price action.
- **Redundancy**: Implementing fallback REST API polling in case WebSocket connections degrade or drop.

## SEC EDGAR Integration
For the Fundamental Analyst Agent, the architecture includes direct API connections to the SEC EDGAR database. It requires custom parsers to strip HTML/XML formatting from 10-K and 10-Q filings, extracting raw financial tables and management discussion sections.

## Financial News and Sentiment
- **Aggregator APIs**: Ingesting from sources like Benzinga Pro or Finnhub.
- **Social Scraping**: Integrating compliant Twitter (X) and Reddit API feeds for momentum tracking.
- **Normalization**: All unstructured text is normalized through an initial low-cost LLM layer (e.g., GPT-4o-mini) to extract entities and sentiment scores before passing to the Debate Workflow.
