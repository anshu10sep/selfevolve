"""
Fundamental Analyst — Real Data Fetching (yfinance)
"""

import logging
from typing import Dict, Any

import yfinance as yf

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


@skill("fundamental_analyst")
async def analyze_financial_statements(ticker: str, period: str = "annual") -> Dict[str, Any]:
    """
    Fetch deep fundamental asset data (P/E, ROE, Debt/Equity, etc.) via yfinance.
    
    Args:
        ticker (str): The stock ticker symbol (e.g., 'AAPL').
        period (str): The period for analysis ('annual' or 'quarterly').
        
    Returns:
        Dict[str, Any]: A dictionary containing core fundamental metrics.
    """
    logger.info(f"Fetching real fundamentals via yfinance for {ticker}")
    
    try:
        # yfinance operations are blocking, but typically fast enough.
        # In a high-throughput async system, we'd run this in a threadpool.
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info or 'symbol' not in info:
            return {"error": f"Could not retrieve fundamental data for {ticker}."}
            
        metrics = {
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "debt_to_equity": info.get("debtToEquity"),
            "return_on_equity": info.get("returnOnEquity"),
            "profit_margin": info.get("profitMargins"),
            "operating_margin": info.get("operatingMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "dividend_yield": info.get("dividendYield"),
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector"),
            "industry": info.get("industry")
        }
        
        # Determine basic value/growth status
        pe = metrics["trailing_pe"]
        growth = metrics["revenue_growth"]
        
        status = "neutral"
        if pe and growth:
            if pe < 15 and growth > 0.10:
                status = "undervalued_growth"
            elif pe > 40 and growth < 0.05:
                status = "overvalued_stagnant"
            elif pe < 15:
                status = "value"
            elif growth > 0.20:
                status = "high_growth"
                
        return {
            "ticker": ticker,
            "period": period,
            "company_name": info.get("longName"),
            "metrics": metrics,
            "analysis_status": status,
            "status": "success"
        }
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {ticker}: {e}")
        return {"error": str(e)}

