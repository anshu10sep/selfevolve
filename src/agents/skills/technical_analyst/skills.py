import pandas as pd
import numpy as np
from typing import Dict, List, Union, Optional

def calculate_sma(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate the Simple Moving Average (SMA).
    
    Args:
        prices (pd.Series): Series of prices.
        period (int): Number of periods for the SMA.
        
    Returns:
        pd.Series: SMA values.
    """
    return prices.rolling(window=period).mean()

def calculate_ema(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate the Exponential Moving Average (EMA).
    
    Args:
        prices (pd.Series): Series of prices.
        period (int): Number of periods for the EMA.
        
    Returns:
        pd.Series: EMA values.
    """
    return prices.ewm(span=period, adjust=False).mean()

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate the Relative Strength Index (RSI) using Wilder's smoothing.
    
    Args:
        prices (pd.Series): Series of prices.
        period (int): Number of periods for the RSI.
        
    Returns:
        pd.Series: RSI values.
    """
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Use exponential moving average for Wilder's RSI
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    Calculate the Moving Average Convergence Divergence (MACD).
    
    Args:
        prices (pd.Series): Series of prices.
        fast_period (int): Fast EMA period.
        slow_period (int): Slow EMA period.
        signal_period (int): Signal line EMA period.
        
    Returns:
        pd.DataFrame: DataFrame containing 'MACD', 'Signal', and 'Histogram'.
    """
    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)
    
    macd = fast_ema - slow_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal
    
    return pd.DataFrame({
        'MACD': macd,
        'Signal': signal,
        'Histogram': histogram
    })

def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.
    
    Args:
        prices (pd.Series): Series of prices.
        period (int): Number of periods for the SMA.
        std_dev (float): Number of standard deviations for the bands.
        
    Returns:
        pd.DataFrame: DataFrame containing 'Upper', 'Middle' (SMA), and 'Lower' bands.
    """
    sma = calculate_sma(prices, period)
    rolling_std = prices.rolling(window=period).std()
    
    upper_band = sma + (rolling_std * std_dev)
    lower_band = sma - (rolling_std * std_dev)
    
    return pd.DataFrame({
        'Upper': upper_band,
        'Middle': sma,
        'Lower': lower_band
    })

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate the Average True Range (ATR).
    
    Args:
        df (pd.DataFrame): DataFrame containing 'High', 'Low', and 'Close' columns.
        period (int): Number of periods for the ATR.
        
    Returns:
        pd.Series: ATR values.
    """
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    return atr

def identify_support_resistance(highs: pd.Series, lows: pd.Series, window: int = 20) -> Dict[str, List[float]]:
    """
    Identify potential support and resistance levels using rolling min/max.
    
    Args:
        highs (pd.Series): Series of high prices.
        lows (pd.Series): Series of low prices.
        window (int): Lookback window to identify local extrema.
        
    Returns:
        Dict[str, List[float]]: Dictionary with 'support' and 'resistance' levels.
    """
    resistance_levels = highs.rolling(window=window, center=True).max().dropna().unique().tolist()
    support_levels = lows.rolling(window=window, center=True).min().dropna().unique().tolist()
    
    # Filter out close levels to avoid clutter
    def filter_levels(levels, threshold=0.01):
        filtered = []
        for level in sorted(levels):
            if not filtered or all(abs(level - f) / f > threshold for f in filtered):
                filtered.append(level)
        return filtered

    return {
        'support': filter_levels(support_levels),
        'resistance': filter_levels(resistance_levels)
    }

def identify_doji(df: pd.DataFrame, threshold: float = 0.1) -> pd.Series:
    """
    Identify Doji candlestick patterns.
    
    Args:
        df (pd.DataFrame): DataFrame containing 'Open', 'High', 'Low', 'Close'.
        threshold (float): Maximum body size as a percentage of the total range.
        
    Returns:
        pd.Series: Boolean series where True indicates a Doji pattern.
    """
    body = (df['Close'] - df['Open']).abs()
    total_range = df['High'] - df['Low']
    
    # Avoid division by zero
    is_doji = (body / total_range.replace(0, np.nan)) <= threshold
    return is_doji.fillna(False)

def generate_technical_summary(df: pd.DataFrame) -> Dict[str, Union[str, float, bool, None]]:
    """
    Generate a summary of technical indicators for the latest data point.
    
    Args:
        df (pd.DataFrame): DataFrame containing 'Open', 'High', 'Low', 'Close' columns.
        
    Returns:
        Dict[str, Union[str, float, bool, None]]: Summary of technical indicators and signals.
    """
    required_cols = ['Open', 'High', 'Low', 'Close']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"DataFrame must contain a '{col}' column.")
            
    close = df['Close']
    
    rsi = calculate_rsi(close).iloc[-1]
    macd_df = calculate_macd(close)
    macd_val = macd_df['MACD'].iloc[-1]
    macd_sig = macd_df['Signal'].iloc[-1]
    
    bb_df = calculate_bollinger_bands(close)
    upper_bb = bb_df['Upper'].iloc[-1]
    lower_bb = bb_df['Lower'].iloc[-1]
    
    atr = calculate_atr(df).iloc[-1]
    is_doji = identify_doji(df).iloc[-1]
    
    current_price = close.iloc[-1]
    
    # Basic signal logic
    signal = "NEUTRAL"
    if rsi < 30 and current_price <= lower_bb:
        signal = "STRONG BUY"
    elif rsi > 70 and current_price >= upper_bb:
        signal = "STRONG SELL"
    elif macd_val > macd_sig and rsi < 60:
        signal = "BUY"
    elif macd_val < macd_sig and rsi > 40:
        signal = "SELL"
        
    return {
        'current_price': float(current_price),
        'rsi': float(rsi) if not pd.isna(rsi) else None,
        'macd': float(macd_val) if not pd.isna(macd_val) else None,
        'macd_signal': float(macd_sig) if not pd.isna(macd_sig) else None,
        'bollinger_upper': float(upper_bb) if not pd.isna(upper_bb) else None,
        'bollinger_lower': float(lower_bb) if not pd.isna(lower_bb) else None,
        'atr': float(atr) if not pd.isna(atr) else None,
        'is_doji': bool(is_doji),
        'overall_signal': signal
    }