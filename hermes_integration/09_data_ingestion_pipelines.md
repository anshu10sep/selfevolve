# Data Ingestion Pipelines

## Target Component
`src/integrations/market_data_daemon.py`

## Architecture Context
Trading relies heavily on pristine data. While standard OHLCV (Open, High, Low, Close, Volume) data is fetched via the Alpaca API, alternative data (e.g., sentiment data, alternative metrics from platforms like TradingView, unusual options activity from proprietary scanners) often requires web scraping.

## Approaches

### Approach 1: Traditional Scrapers (BeautifulSoup/Requests)
Maintain custom Python scrapers for alternative data sources.
- **Pros**: Fast execution, highly specific.
- **Cons**: Easily blocked by Cloudflare or advanced bot-protection. Requires constant maintenance as target websites update their DOM.

### Approach 2: Hermes Browser Control with Stealth
Delegate alternative data gathering to Hermes using its integrated browser control. Hermes can navigate sites like a human, solving simple captchas, executing JavaScript, and extracting data semantically.
- **Pros**: Bypasses most anti-bot protections; robust against minor DOM changes because it extracts data semantically rather than relying on strict CSS selectors.
- **Cons**: Resource intensive.

## Recommendation: Approach 2 (Hermes Browser Control)
The maintenance burden of traditional scrapers is too high for a self-evolving system. Using Hermes' semantic browser control ensures the data ingestion pipelines for alternative data remain robust and require significantly less manual patching.
