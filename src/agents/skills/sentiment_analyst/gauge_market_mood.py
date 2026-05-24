def gauge_market_mood(social_media_sentiment: float, news_sentiment: float, investor_surveys: dict) -> dict:
    """
    Aggregates various sentiment indicators to provide an overall gauge of the market's mood.

    Args:
        social_media_sentiment: A numerical score representing sentiment from social media.
        news_sentiment: A numerical score representing sentiment from news.
        investor_surveys: A dictionary of results from investor sentiment surveys.

    Returns:
        A dictionary with an overall market mood score and a qualitative assessment.
    """
    print("Gauging overall market mood.")
    overall_score = (social_media_sentiment * 0.3) + (news_sentiment * 0.3) + (investor_surveys.get("bullish_percentage", 0) * 0.01 * 0.4)
    if overall_score > 0.6:
        assessment = "optimistic"
    elif overall_score < 0.4:
        assessment = "pessimistic"
    else:
        assessment = "neutral"
    return {"overall_mood_score": overall_score, "assessment": assessment}
