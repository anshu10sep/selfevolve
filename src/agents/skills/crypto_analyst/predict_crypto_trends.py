def predict_crypto_trends(historical_data: dict, news_sentiment: str) -> dict:
    """
    Predicts short-term and long-term trends for specific cryptocurrencies based on historical data and sentiment.

    Args:
        historical_data: A dictionary of historical price, volume, and other relevant data.
        news_sentiment: An aggregated sentiment score from recent news.

    Returns:
        A dictionary containing trend predictions (e.g., "bullish", "bearish", "sideways") and confidence levels.
    """
    print(f"Predicting crypto trends based on historical data and sentiment: {news_sentiment}")
    # Placeholder for actual predictive model
    if historical_data.get("price_change_7d", 0) > 0.1 and news_sentiment == "positive":
        return {"short_term": "bullish", "long_term": "bullish", "confidence": 0.75}
    elif historical_data.get("price_change_7d", 0) < -0.05 and news_sentiment == "negative":
        return {"short_term": "bearish", "long_term": "bearish", "confidence": 0.60}
    return {"short_term": "sideways", "long_term": "uncertain", "confidence": 0.40}
===