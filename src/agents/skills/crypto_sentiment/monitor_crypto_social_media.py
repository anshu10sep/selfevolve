def monitor_crypto_social_media(keywords: list, platforms: list) -> dict:
    """
    Monitors specified social media platforms for mentions of cryptocurrencies and extracts sentiment.

    Args:
        keywords: A list of cryptocurrency-related keywords to monitor (e.g., ["Bitcoin", "Ethereum", "$BTC"]).
        platforms: A list of social media platforms to monitor (e.g., ["Twitter", "Reddit"]).

    Returns:
        A dictionary containing aggregated sentiment scores and trending topics from social media.
    """
    print(f"Monitoring social media for keywords: {', '.join(keywords)} on platforms: {', '.join(platforms)}")
    # Placeholder for actual social media scraping and NLP
    sentiment_score = 0.65 # Example positive sentiment
    trending_topics = ["ETH2.0", "NFTs", "Metaverse"]
    return {"social_media_sentiment_score": sentiment_score, "trending_topics": trending_topics}
