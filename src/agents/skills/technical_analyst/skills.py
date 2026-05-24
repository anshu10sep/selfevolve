import pandas as pd
import numpy as np
from typing import List, Dict, Union, Optional

def calculate_sma(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate the Simple Moving Average (SMA) for a given list of prices.
    
    Args:
        prices (List[float]): List of historical prices.
        period (int): The number of periods to calculate the SMA over.
        
    Returns:
        List[float]: A list of SMA values. The first `period - 1` values will be NaN.
    """
    series = pd.Series(prices)
    sma = series.rolling(window=period).mean()
    return sma.fillna(float('nan')).tolist()

def calculate_ema(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate the Exponential Moving Average (EMA) for a given list of prices.
    
    Args:
        prices (List[float]): List of historical prices.
        period (int): The number of periods to calculate the EMA over.
        
    Returns:
        List[float]: A list of EMA values.
    """
    series = pd.Series(prices)
    ema = series.ewm(span=period, adjust=False).mean()
    return ema.fillna(float('nan')).tolist()

def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate the Relative Strength Index (RSI) for a given list of prices.
    
    Args:
        prices (List[float]): List of historical prices.
        period (int): The number of periods to calculate the RSI over.
        
    Returns:
        List[float]: A list of RSI values.
    """
    series = pd.Series(prices)
    delta = series.diff()
    
    # Calculate gains and losses
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    # Calculate exponential moving average of gains and losses
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.fillna(float('nan')).tolist()

def calculate_macd(prices: List[float], fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Dict[str, List[float]]:
    """
    Calculate the Moving Average Convergence Divergence (MACD).
    
    Args:
        prices (List[float]): List of historical prices.
        fast_period (int): The fast EMA period.
        slow_period (int): The slow EMA period.
        signal_period (int): The signal line EMA period.
        
    Returns:
        Dict[str, List[float]]: A dictionary containing 'macd', 'signal', and 'histogram'.
    """
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast_period, adjust=False).mean()
    ema_slow = series.ewm(span=slow_period, adjust=False).mean()
    
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal
    
    return {
        "macd": macd.fillna(float('nan')).tolist(),
        "signal": signal.fillna(float('nan')).tolist(),
        "histogram": histogram.fillna(float('nan')).tolist()
    }

def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Dict[str, List[float]]:
    """
    Calculate Bollinger Bands.
    
    Args:
        prices (List[float]): List of historical prices.
        period (int): The SMA period.
        std_dev (float): The number of standard deviations for the bands.
        
    Returns:
        Dict[str, List[float]]: A dictionary containing 'upper_band', 'middle_band', and 'lower_band'.
    """
    series = pd.Series(prices)
    middle_band = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    
    upper_band = middle_band + (std * std_dev)
    lower_band = middle_band - (std * std_dev)
    
    return {
        "upper_band": upper_band.fillna(float('nan')).tolist(),
        "middle_band": middle_band.fillna(float('nan')).tolist(),
        "lower_band": lower_band.fillna(float('nan')).tolist()
    }

def identify_support_resistance(prices: List[float], window: int = 5) -> Dict[str, List[float]]:
    """
    Identify potential support and resistance levels using local minima and maxima.
    
    Args:
        prices (List[float]): List of historical prices.
        window (int): The window size to check for local extrema.
        
    Returns:
        Dict[str, List[float]]: Dictionary containing lists of 'support_levels' and 'resistance_levels'.
    """
    supports = []
    resistances = []
    
    for i in range(window, len(prices) - window):
        is_support = True
        is_resistance = True
        
        for j in range(1, window + 1):
            if prices[i] > prices[i - j] or prices[i] > prices[i + j]:
                is_support = False
            if prices[i] < prices[i - j] or prices[i] < prices[i + j]:
                is_resistance = False
                
        if is_support:
            supports.append(prices[i])
        if is_resistance:
            resistances.append(prices[i])
            
    return {
        "support_levels": supports,
        "resistance_levels": resistances
    }

def identify_trend(prices: List[float], period: int = 14) -> str:
    """
    Identify the current trend based on SMA and recent price action.
    
    Args:
        prices (List[float]): List of historical prices.
        period (int): The period to use for trend analysis.
        
    Returns:
        str: 'bullish', 'bearish', or 'neutral'.
    """
    if len(prices) < period:
        return "neutral"
        
    sma = calculate_sma(prices, period)
    current_price = prices[-1]
    current_sma = sma[-1]
    
    if pd.isna(current_sma):
        return "neutral"
        
    if current_price > current_sma * 1.01:
        return "bullish"
    elif current_price < current_sma * 0.99:
        return "bearish"
    else:
        return "neutral"

def get_technical_summary(prices: List[float]) -> Dict[str, Union[float, str, bool]]:
    """
    Get a summary of technical indicators for the latest price point.
    
    Args:
        prices (List[float]): List of historical prices.
        
    Returns:
        Dict[str, Union[float, str, bool]]: A dictionary of the latest indicator values and trend.
    """
    if len(prices) < 26:
        return {"error": "Not enough data points. Minimum 26 required."}
        
    rsi = calculate_rsi(prices, 14)[-1]
    macd_data = calculate_macd(prices)
    macd = macd_data["macd"][-1]
    signal = macd_data["signal"][-1]
    trend = identify_trend(prices, 20)
    
    return {
        "current_price": prices[-1],
        "rsi_14": rsi if not pd.isna(rsi) else 0.0,
        "macd": macd if not pd.isna(macd) else 0.0,
        "macd_signal": signal if not pd.isna(signal) else 0.0,
        "trend": trend,
        "is_overbought": bool(rsi > 70) if not pd.isna(rsi) else False,
        "is_oversold": bool(rsi < 30) if not pd.isna(rsi) else False
    }