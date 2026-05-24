def identify_bearish_signals(market_data: dict) -> list:
    """
    Analyzes market data to identify potential bearish signals.

    Args:
        market_data: A dictionary containing various market indicators (e.g., price, volume, news sentiment).

    Returns:
        A list of identified bearish signals, if any.
    """
    print(f"Identifying bearish signals from market data: {market_data.get('symbol', 'N/A')}")
    signals = []
    if market_data.get("price_trend") == "downward" and market_data.get("volume_trend") == "increasing":
        signals.append("High volume downward trend")
    if market_data.get("news_sentiment") == "negative" and market_data.get("rsi") < 30:
        signals.append("Negative sentiment with oversold conditions")
    return signals
