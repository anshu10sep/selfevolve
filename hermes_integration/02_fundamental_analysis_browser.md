# Fundamental Analysis Web Control

## Target Component
`src/agents/fundamental_analyst_agent.py`

## Architecture Context
The Fundamental Analyst Agent currently relies heavily on structured API data (e.g., Alpaca, Market Data). However, alpha in fundamental trading often comes from unstructured data: live SEC filings, immediate press releases, and earnings call transcripts hosted on dynamic web pages. Standard `requests` or `BeautifulSoup` scrapers fail on modern SPAs (Single Page Applications).

## Approaches

### Approach 1: API-based Extraction using Hermes Web Search
Utilize Hermes' native web search capabilities to query for news events and fetch plain-text summaries from pre-indexed search engines.
- **Pros**: Fast, token-efficient, and easy to implement.
- **Cons**: Limited to what search engines have indexed. High latency for breaking news (SEC 8-K filings).

### Approach 2: Hermes Headless Playwright Integration
Deploy a Hermes sub-agent equipped with full browser automation (Playwright). The agent can navigate directly to the SEC EDGAR database or investor relations pages, bypass basic anti-bot screens, and scrape the raw, real-time data immediately as it is published.
- **Pros**: Direct access to real-time unstructured data, capability to handle JavaScript-heavy sites.
- **Cons**: Slower execution time per request, higher token usage for HTML DOM parsing.

## Recommendation: Approach 2 (Hermes Headless Playwright)
To achieve true edge in fundamental analysis, the system must process data the second it is released, rather than waiting for search engine indexing or third-party API updates. Using Hermes' browser control allows the fundamental agent to directly monitor source URLs.
