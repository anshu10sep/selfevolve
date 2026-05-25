"""
Macro Analyst — Real Market Breadth Analysis using SPY/QQQ
"""

import logging
from typing import Dict, Any

from agents.skills.validator import skill
from broker.alpaca_client import AlpacaClient
from agents.skills.macro_analyst.analyze_global_economy import compute_market_regime

logger = logging.getLogger(__name__)


@skill("macro_analyst")
async def analyze_market_breadth() -> Dict[str, Any]:
    """
    Analyze the broader market regime using major ETFs (SPY, QQQ, IWM)
    to proxy macroeconomic risk and market breadth.
    
    Returns:
        Dict[str, Any]: A dictionary containing the market regime, composite score, and ETF returns.
    """
    logger.info("Fetching macro market breadth data")
    alpaca = AlpacaClient()
    
    try:
        # Fetch 30 days of data for major indices
        # SPY = S&P 500 (Broad Market)
        # QQQ = Nasdaq 100 (Tech/Growth)
        # IWM = Russell 2000 (Small Caps)
        etfs = ["SPY", "QQQ", "IWM"]
        
        returns_30d = {}
        for ticker in etfs:
            bars = await alpaca.get_bars(ticker, timeframe="1Day", limit=30)
            if bars and len(bars) >= 2:
                start_price = bars[0].get("c", 0)
                end_price = bars[-1].get("c", 0)
                if start_price > 0:
                    returns_30d[ticker] = (end_price - start_price) / start_price
                else:
                    returns_30d[ticker] = 0.0
            else:
                returns_30d[ticker] = 0.0
                
        await alpaca.close()
        
        spy_return = returns_30d.get("SPY", 0.0)
        qqq_return = returns_30d.get("QQQ", 0.0)
        iwm_return = returns_30d.get("IWM", 0.0)
        
        # Proxy VIX based on recent market drop (inverse of return, highly simplified)
        # If SPY drops 5%, proxy VIX goes up. Base VIX ~15.
        vix_proxy = max(10.0, 15.0 - (spy_return * 200))
        
        # Proxy breadth: if IWM (small caps) is outperforming SPY, breadth is good
        breadth_ratio = 1.0 + (iwm_return - spy_return)
        
        # Analyze regime using the core macro logic
        regime_data = compute_market_regime(
            vix_level=vix_proxy,
            market_return_30d=spy_return,
            breadth_ratio=breadth_ratio,
            correlation_avg=0.5 # Default correlation
        )
        
        return {
            "etf_returns_30d": {
                "SPY": round(spy_return, 4),
                "QQQ": round(qqq_return, 4),
                "IWM": round(iwm_return, 4)
            },
            "proxies": {
                "vix_proxy": round(vix_proxy, 2),
                "breadth_ratio_proxy": round(breadth_ratio, 2)
            },
            "regime_analysis": regime_data,
            "status": "success"
        }
        
    except Exception as e:
        await alpaca.close()
        logger.error(f"Error fetching market breadth: {e}")
        return {"error": str(e)}

