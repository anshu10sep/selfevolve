"""
Sentiment Analyst — Real News Fetching and Sentiment Analysis
"""

import logging
from typing import Dict, Any

from agents.skills.validator import skill
from broker.alpaca_client import AlpacaClient
from agents.skills.sentiment_analyst.analyze_news_articles import analyze_news_sentiment

logger = logging.getLogger(__name__)


@skill("sentiment_analyst")
async def analyze_ticker_sentiment(ticker: str, limit: int = 20) -> Dict[str, Any]:
    """
    Fetch the latest news for a ticker from Alpaca and analyze its sentiment.
    
    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        limit (int): Number of recent news articles to fetch (default 20).
        
    Returns:
        Dict[str, Any]: A dictionary containing the sentiment score, dominant sentiment, and article breakdowns.
    """
    logger.info(f"Fetching news and analyzing sentiment for {ticker}")
    alpaca = AlpacaClient()
    
    try:
        # Fetch news articles
        news_items = await alpaca.get_news(ticker, limit=limit)
        await alpaca.close()
        
        if not news_items:
            return {
                "sentiment_score": 0.0,
                "dominant_sentiment": "neutral",
                "confidence": 0.0,
                "article_count": 0,
                "interpretation": f"No recent news found for {ticker}."
            }
            
        # Extract headlines and summaries
        headlines = []
        for item in news_items:
            # Alpaca news items have 'headline' and 'summary'
            headline = item.get("headline", "")
            summary = item.get("summary", "")
            # Combine them for deeper sentiment analysis
            text = f"{headline}. {summary}"
            headlines.append(text)
            
        # Analyze sentiment
        sentiment_results = analyze_news_sentiment(headlines)
        sentiment_results["ticker"] = ticker
        
        return sentiment_results
        
    except Exception as e:
        await alpaca.close()
        logger.error(f"Error analyzing sentiment for {ticker}: {e}")
        return {"error": str(e)}

