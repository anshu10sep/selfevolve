def monitor_social_media(keywords: list, platforms: list) -> dict:
    """
    Monitors specified social media platforms for mentions of companies or assets and extracts sentiment.

    Args:
        keywords: A list of keywords to monitor (e.g., ["AAPL", "Tesla", "#stockmarket"]).
        platforms: A list of social media platforms to monitor (e.g., ["Twitter", "Reddit", "StockTwits"]).

    Returns:
        A dictionary containing aggregated sentiment scores and trending topics from social media.
    """
    print(f"Monitoring social media for keywords: {', '.join(keywords)} on platforms: {', '.join(platforms)}")
    # Placeholder for actual social media scraping and NLP
    sentiment_score = 0.55 # Example slightly positive sentiment
    trending_topics = ["AI_boom", "interest_rate_hike_fears"]
    return {"social_media_sentiment_score": sentiment_score, "trending_topics": trending_topics}
===