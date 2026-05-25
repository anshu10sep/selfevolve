"""
Technical Analyst — Real Indicator Tools (pandas_ta)

Production-grade technical indicator calculations using pandas_ta.
These replace the custom numpy implementations for maximum scalability
and standard compliance.
"""

from typing import Dict, Any, List
import logging
import pandas as pd
import pandas_ta as ta

from agents.skills.validator import skill

logger = logging.getLogger(__name__)


@skill("technical_analyst")
def compute_rsi(prices: List[float], period: int = 14) -> Dict[str, Any]:
    """Compute the Relative Strength Index (RSI) using pandas_ta.

    Args:
        prices: List of closing prices.
        period: RSI calculation period (default 14).

    Returns:
        Dict with rsi_value, signal (overbought/oversold/neutral), and interpretation.
    """

    if len(prices) < period + 1:
        return {
            "rsi_value": None,
            "signal": "insufficient_data",
            "interpretation": f"Need at least {period + 1} prices, got {len(prices)}.",
        }

    df = pd.DataFrame({"close": prices})
    df.ta.rsi(length=period, append=True)
    
    rsi = df[f"RSI_{period}"].iloc[-1]
    if pd.isna(rsi):
        rsi = 100.0  # Fallback if division by zero occurred initially
    
    rsi = round(float(rsi), 2)

    if rsi >= 70:
        signal = "overbought"
        interpretation = f"RSI({period}) = {rsi}. Overbought territory — potential reversal or pullback."
    elif rsi <= 30:
        signal = "oversold"
        interpretation = f"RSI({period}) = {rsi}. Oversold territory — potential bounce or reversal."
    else:
        signal = "neutral"
        interpretation = f"RSI({period}) = {rsi}. Neutral momentum — no extreme conditions."

    return {
        "indicator": "RSI",
        "rsi_value": rsi,
        "period": period,
        "signal": signal,
        "interpretation": interpretation,
    }


@skill("technical_analyst")
def compute_macd(
    prices: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Dict[str, Any]:
    """
    Compute MACD using pandas_ta.
    
    Args:
        prices (List[float]): List of closing prices.
        fast_period (int): Fast EMA period.
        slow_period (int): Slow EMA period.
        signal_period (int): Signal EMA period.
        
    Returns:
        Dict[str, Any]: MACD line, signal line, histogram, and signal.
    """
    min_length = slow_period + signal_period
    if len(prices) < min_length:
        return {
            "macd_line": None,
            "signal_line": None,
            "histogram": None,
            "signal": "insufficient_data",
            "interpretation": f"Need at least {min_length} prices, got {len(prices)}.",
        }

    df = pd.DataFrame({"close": prices})
    macd_df = df.ta.macd(fast=fast_period, slow=slow_period, signal=signal_period, append=False)
    
    macd_col = f"MACD_{fast_period}_{slow_period}_{signal_period}"
    hist_col = f"MACDh_{fast_period}_{slow_period}_{signal_period}"
    sig_col = f"MACDs_{fast_period}_{slow_period}_{signal_period}"

    macd_current = round(float(macd_df[macd_col].iloc[-1]), 4)
    signal_current = round(float(macd_df[sig_col].iloc[-1]), 4)
    histogram = round(float(macd_df[hist_col].iloc[-1]), 4)

    macd_prev = round(float(macd_df[macd_col].iloc[-2]), 4)
    signal_prev = round(float(macd_df[sig_col].iloc[-2]), 4)

    if macd_prev <= signal_prev and macd_current > signal_current:
        signal = "bullish_crossover"
        interpretation = f"MACD: Bullish crossover. MACD={macd_current} > signal={signal_current}."
    elif macd_prev >= signal_prev and macd_current < signal_current:
        signal = "bearish_crossover"
        interpretation = f"MACD: Bearish crossover. MACD={macd_current} < signal={signal_current}."
    elif macd_current > signal_current:
        signal = "bullish"
        interpretation = f"MACD: Bullish. MACD={macd_current} > signal={signal_current}."
    else:
        signal = "bearish"
        interpretation = f"MACD: Bearish. MACD={macd_current} < signal={signal_current}."

    return {
        "indicator": "MACD",
        "macd_line": macd_current,
        "signal_line": signal_current,
        "histogram": histogram,
        "signal": signal,
        "interpretation": interpretation,
    }


@skill("technical_analyst")
def compute_bollinger_bands(
    prices: List[float], period: int = 20, std_multiplier: float = 2.0
) -> Dict[str, Any]:
    """
    Compute Bollinger Bands using pandas_ta.
    
    Args:
        prices (List[float]): List of closing prices.
        period (int): SMA period.
        std_multiplier (float): Standard deviation multiplier.
        
    Returns:
        Dict[str, Any]: Upper, middle, and lower bands.
    """
    if len(prices) < period:
        return {
            "upper_band": None,
            "middle_band": None,
            "lower_band": None,
            "signal": "insufficient_data",
            "interpretation": f"Need at least {period} prices.",
        }

    df = pd.DataFrame({"close": prices})
    bb_df = df.ta.bbands(length=period, std=std_multiplier, append=False)
    
    # Columns typically format: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
    lower_col = [c for c in bb_df.columns if c.startswith('BBL')][0]
    mid_col = [c for c in bb_df.columns if c.startswith('BBM')][0]
    upper_col = [c for c in bb_df.columns if c.startswith('BBU')][0]
    pct_col = [c for c in bb_df.columns if c.startswith('BBP')][0]
    bw_col = [c for c in bb_df.columns if c.startswith('BBB')][0]

    current_price = prices[-1]
    upper = round(float(bb_df[upper_col].iloc[-1]), 4)
    middle = round(float(bb_df[mid_col].iloc[-1]), 4)
    lower = round(float(bb_df[lower_col].iloc[-1]), 4)
    pct_b = round(float(bb_df[pct_col].iloc[-1]), 4)
    bandwidth = round(float(bb_df[bw_col].iloc[-1]), 4)

    if current_price > upper:
        signal = "above_upper_band"
        interpretation = f"BB: Price ${current_price:.2f} is ABOVE upper band. %B={pct_b:.2f}."
    elif current_price < lower:
        signal = "below_lower_band"
        interpretation = f"BB: Price ${current_price:.2f} is BELOW lower band. %B={pct_b:.2f}."
    else:
        signal = "within_bands"
        interpretation = f"BB: Price within bands. %B={pct_b:.2f}."

    return {
        "indicator": "BollingerBands",
        "upper_band": upper,
        "middle_band": middle,
        "lower_band": lower,
        "bandwidth": bandwidth,
        "percent_b": pct_b,
        "current_price": current_price,
        "signal": signal,
        "interpretation": interpretation,
    }


@skill("technical_analyst")
def compute_moving_averages(
    prices: List[float], short_period: int = 10, long_period: int = 50
) -> Dict[str, Any]:
    """
    Compute Simple Moving Averages using pandas_ta.
    
    Args:
        prices (List[float]): List of closing prices.
        short_period (int): Short-term SMA period.
        long_period (int): Long-term SMA period.
        
    Returns:
        Dict[str, Any]: Short and long SMAs, and trend interpretation.
    """
    if len(prices) < long_period + 1:
        return {
            "short_sma": None,
            "long_sma": None,
            "signal": "insufficient_data",
            "interpretation": f"Need at least {long_period + 1} prices.",
        }

    df = pd.DataFrame({"close": prices})
    df.ta.sma(length=short_period, append=True)
    df.ta.sma(length=long_period, append=True)
    
    short_col = f"SMA_{short_period}"
    long_col = f"SMA_{long_period}"

    short_sma = round(float(df[short_col].iloc[-1]), 4)
    long_sma = round(float(df[long_col].iloc[-1]), 4)
    
    prev_short = round(float(df[short_col].iloc[-2]), 4)
    prev_long = round(float(df[long_col].iloc[-2]), 4)

    if prev_short <= prev_long and short_sma > long_sma:
        signal = "golden_cross"
        trend = "bullish"
    elif prev_short >= prev_long and short_sma < long_sma:
        signal = "death_cross"
        trend = "bearish"
    elif short_sma > long_sma:
        signal = "bullish_trend"
        trend = "bullish"
    else:
        signal = "bearish_trend"
        trend = "bearish"

    current_price = prices[-1]
    above_short = current_price > short_sma
    above_long = current_price > long_sma

    return {
        "indicator": "SMA",
        "short_sma": short_sma,
        "long_sma": long_sma,
        "current_price": current_price,
        "signal": signal,
        "trend": trend,
        "above_short_sma": above_short,
        "above_long_sma": above_long,
        "interpretation": f"SMA({short_period})={short_sma:.2f}, SMA({long_period})={long_sma:.2f}. Signal: {signal}",
    }


@skill("technical_analyst")
def compute_volume_analysis(
    prices: List[float], volumes: List[float], period: int = 20
) -> Dict[str, Any]:
    """
    Analyze volume trends relative to price changes.
    
    Args:
        prices (List[float]): List of closing prices.
        volumes (List[float]): List of volumes.
        period (int): SMA period for average volume.
        
    Returns:
        Dict[str, Any]: Volume analysis signals.
    """
    if len(prices) < period or len(volumes) < period:
        return {
            "signal": "insufficient_data",
            "interpretation": f"Need at least {period} data points.",
        }

    df = pd.DataFrame({"close": prices, "volume": volumes})
    df.ta.sma(close="volume", length=period, append=True)
    
    avg_vol_col = f"SMA_{period}"
    current_vol = float(df["volume"].iloc[-1])
    avg_vol = float(df[avg_vol_col].iloc[-1])
    
    volume_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 0
    price_change = float(df["close"].iloc[-1] - df["close"].iloc[-2])

    if volume_ratio > 2.0 and price_change > 0:
        signal = "volume_breakout_bullish"
    elif volume_ratio > 2.0 and price_change < 0:
        signal = "volume_breakout_bearish"
    elif volume_ratio > 1.5:
        signal = "above_average_volume"
    elif volume_ratio < 0.5:
        signal = "low_volume"
    else:
        signal = "normal_volume"

    return {
        "indicator": "VolumeAnalysis",
        "current_volume": current_vol,
        "average_volume": round(avg_vol, 0),
        "volume_ratio": volume_ratio,
        "price_change": round(price_change, 4),
        "signal": signal,
        "interpretation": f"Volume at {volume_ratio}x average.",
    }
