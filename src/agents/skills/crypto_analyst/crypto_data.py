import yfinance as yf
import pandas as pd
import logging
import time
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class CryptoDataError(Exception):
    """Custom exception for crypto data errors."""
    pass

def fetch_crypto_data_with_retry(symbol: str, period: str = "5d", interval: str = "1d", retries: int = 3) -> pd.DataFrame:
    """
    Fetches historical data for a given cryptocurrency with retry logic.
    
    Args:
        symbol (str): The cryptocurrency ticker symbol (e.g., 'BTC-USD').
        period (str): The time period to fetch (default '5d').
        interval (str): The data interval (default '1d').
        retries (int): Number of retry attempts.
        
    Returns:
        pd.DataFrame: Historical price data.
    """
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if not df.empty:
                return df
            logger.warning(f"Attempt {attempt + 1}: Empty data returned for {symbol}")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}: Failed to fetch data for {symbol}: {str(e)}")
            
        time.sleep(2 ** attempt) # Exponential backoff
        
    logger.error(f"All {retries} attempts failed for {symbol}")
    return pd.DataFrame()

def screen_crypto_market(tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Screens the crypto market and returns metrics for the provided tickers.
    If no tickers are provided, uses a default list of major cryptocurrencies.
    
    Args:
        tickers (List[str], optional): List of ticker symbols to screen.
        
    Returns:
        List[Dict]: A list of dictionaries containing market metrics for each ticker.
    """
    if tickers is None:
        tickers = [
            'BTC-USD', 'ETH-USD', 'BNB-USD', 'SOL-USD', 'XRP-USD',
            'ADA-USD', 'AVAX-USD', 'DOGE-USD', 'DOT-USD', 'LINK-USD'
        ]
        
    results = []
    failed_tickers = []
    
    for ticker in tickers:
        try:
            df = fetch_crypto_data_with_retry(ticker, period="5d", interval="1d")
            if df.empty or len(df) < 2:
                failed_tickers.append(ticker)
                continue
                
            current_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            volume = df['Volume'].iloc[-1]
            
            change_pct = ((current_close - prev_close) / prev_close) * 100
            
            # Attempt to get market cap
            try:
                info = yf.Ticker(ticker).info
                market_cap = info.get('marketCap', 0)
            except Exception:
                market_cap = 0
                
            results.append({
                'symbol': ticker,
                'price': float(current_close),
                'change_pct': float(change_pct),
                'volume': float(volume),
                'market_cap': float(market_cap)
            })
            
        except Exception as e:
            logger.error(f"Error screening {ticker}: {str(e)}")
            failed_tickers.append(ticker)
            
    if not results:
        error_msg = f"crypto_screening_failed: Could not fetch data for any tickers. Failed: {failed_tickers}"
        logger.error(error_msg)
        # Return empty list instead of raising to prevent crashing the agent loop
        return []
        
    if failed_tickers:
        logger.warning(f"crypto_screening partially failed. Could not fetch: {failed_tickers}")
        
    # Sort by market cap descending
    results.sort(key=lambda x: x['market_cap'], reverse=True)
    return results

def get_crypto_screening_summary() -> Dict[str, Any]:
    """
    Returns a summary of the crypto screening, including top gainers and losers.
    
    Returns:
        Dict: A summary dictionary containing status, top gainers, top losers, and raw data.
    """
    try:
        market_data = screen_crypto_market()
        if not market_data:
            logger.error("crypto_screening_failed: No market data retrieved.")
            return {"status": "error", "message": "crypto_screening_failed"}
            
        gainers = sorted(market_data, key=lambda x: x['change_pct'], reverse=True)
        losers = sorted(market_data, key=lambda x: x['change_pct'])
        
        return {
            "status": "success",
            "total_screened": len(market_data),
            "top_gainers": gainers[:3],
            "top_losers": losers[:3],
            "market_data": market_data
        }
    except Exception as e:
        logger.error(f"crypto_screening_failed during summary generation: {str(e)}")
        return {"status": "error", "message": f"crypto_screening_failed: {str(e)}"}