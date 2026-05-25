"""
Technical Analyst — Real Data Fetching and Indicator Analysis
"""

import logging
from typing import Dict, Any

from agents.skills.validator import skill
from broker.alpaca_client import AlpacaClient
from agents.skills.technical_analyst.indicator_analysis import (
    compute_rsi,
    compute_macd,
    compute_bollinger_bands,
    compute_moving_averages
)

logger = logging.getLogger(__name__)


@skill("technical_analyst")
async def analyze_technical_indicators(ticker: str) -> Dict[str, Any]:
    """
    Fetch the latest market data for a ticker and perform comprehensive technical analysis.
    This includes RSI, MACD, Bollinger Bands, and Moving Averages.
    
    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        
    Returns:
        Dict[str, Any]: A dictionary containing comprehensive technical indicator results.
    """
    logger.info(f"Fetching data and calculating indicators for {ticker}")
    
    alpaca = AlpacaClient()
    try:
        # Fetch 60 days of data to ensure enough periods for a 50-day SMA and MACD
        bars = await alpaca.get_bars(ticker, timeframe="1Day", limit=60)
        await alpaca.close()
        
        if not bars or len(bars) < 50:
            return {
                "error": f"Insufficient data for {ticker}. Need at least 50 days, got {len(bars)}."
            }
            
        prices = [bar["c"] for bar in bars] # Assuming 'c' is close in Alpaca bar response
        volumes = [bar["v"] for bar in bars]
        
        # Calculate indicators
        rsi_data = compute_rsi(prices, period=14)
        macd_data = compute_macd(prices, fast_period=12, slow_period=26, signal_period=9)
        bb_data = compute_bollinger_bands(prices, period=20, std_multiplier=2.0)
        ma_data = compute_moving_averages(prices, short_period=10, long_period=50)
        
        current_price = prices[-1]
        
        # Formulate an overall technical consensus
        bullish_signals = 0
        bearish_signals = 0
        
        if rsi_data.get("signal") == "oversold": bullish_signals += 1
        elif rsi_data.get("signal") == "overbought": bearish_signals += 1
        
        if macd_data.get("signal") in ("bullish", "bullish_crossover"): bullish_signals += 1
        elif macd_data.get("signal") in ("bearish", "bearish_crossover"): bearish_signals += 1
        
        if ma_data.get("trend") == "bullish": bullish_signals += 1
        elif ma_data.get("trend") == "bearish": bearish_signals += 1
        
        if bullish_signals > bearish_signals:
            consensus = "BULLISH"
        elif bearish_signals > bullish_signals:
            consensus = "BEARISH"
        else:
            consensus = "NEUTRAL"
            
        return {
            "ticker": ticker,
            "current_price": current_price,
            "data_points": len(prices),
            "rsi": rsi_data,
            "macd": macd_data,
            "bollinger_bands": bb_data,
            "moving_averages": ma_data,
            "summary": {
                "bullish_signals": bullish_signals,
                "bearish_signals": bearish_signals,
                "consensus": consensus
            }
        }
        
    except Exception as e:
        await alpaca.close()
        logger.error(f"Error fetching data for {ticker}: {e}")
        return {"error": str(e)}
