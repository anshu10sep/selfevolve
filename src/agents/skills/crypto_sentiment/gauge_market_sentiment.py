def gauge_market_sentiment(social_media_sentiment: float, news_sentiment: float, funding_rates: dict) -> dict:
    """
    Aggregates various sentiment indicators to provide an overall gauge of the crypto market's mood.

    Args:
        social_media_sentiment: A numerical score representing sentiment from social media.
        news_sentiment: A numerical score representing sentiment from news.
        funding_rates: A dictionary of funding rates for perpetual futures.

    Returns:
        A dictionary with an overall market sentiment score and a qualitative assessment.
    """
    print("Gauging overall crypto market sentiment.")
    overall_score = (social_media_sentiment * 0.4) + (news_sentiment * 0.4) + (funding_rates.get("average", 0) * 0.2)
    if overall_score > 0.5:
        assessment = "bullish"
    elif overall_score < -0.5:
        assessment = "bearish"
    else:
        assessment = "neutral"
    return {"overall_sentiment_score": overall_score, "assessment": assessment}
===