"""
Skills for the Technical Analyst agent.

This module provides tools for analyzing technical indicators, recognizing chart patterns,
and predicting future price movements based on historical market data.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional

def calculate_rsi(data: pd.Series, periods: int = 14) -> pd.Series:
    """
    Calculate the Relative Strength Index (RSI).
    
    Args:
        data (pd.Series): Series of prices (usually closing prices).
        periods (int): Number of periods to use for RSI calculation.
        
    Returns:
        pd.Series: RSI values.
    """
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        data (pd.Series): Series of prices.
        fast (int): Fast EMA period.
        slow (int): Slow EMA period.
        signal (int): Signal line EMA period.
        
    Returns:
        Dict[str, pd.Series]: Dictionary containing 'macd', 'signal', and 'histogram' series.
    """
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return {'macd': macd, 'signal': signal_line, 'histogram': histogram}

def analyze_indicators(price_data: pd.DataFrame, indicators: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Calculates and analyzes technical indicators for the given price data.
    
    Args:
        price_data (pd.DataFrame): Historical price data containing at least a 'close' column.
        indicators (List[str], optional): List of indicators to calculate. 
                                          Defaults to ['RSI', 'MACD', 'SMA_20', 'SMA_50'].
        
    Returns:
        Dict[str, Any]: A dictionary containing the latest indicator values and a summary signal.
    """
    if indicators is None:
        indicators = ['RSI', 'MACD', 'SMA_20', 'SMA_50']
        
    results = {}
    signals = []
    
    if 'close' not in price_data.columns:
        raise ValueError("price_data must contain a 'close' column")
        
    close_prices = price_data['close']
    
    if 'RSI' in indicators:
        rsi = calculate_rsi(close_prices)
        latest_rsi = rsi.iloc[-1] if not rsi.empty else None
        results['RSI'] = latest_rsi
        if latest_rsi is not None:
            if latest_rsi > 70:
                signals.append("Overbought (RSI > 70)")
            elif latest_rsi < 30:
                signals.append("Oversold (RSI < 30)")
            else:
                signals.append("Neutral RSI")
                
    if 'MACD' in indicators:
        macd_data = calculate_macd(close_prices)
        latest_macd = macd_data['macd'].iloc[-1] if not macd_data['macd'].empty else None
        latest_signal = macd_data['signal'].iloc[-1] if not macd_data['signal'].empty else None
        results['MACD'] = {'macd': latest_macd, 'signal': latest_signal}
        if latest_macd is not None and latest_signal is not None:
            if latest_macd > latest_signal:
                signals.append("Bullish MACD Crossover")
            else:
                signals.append("Bearish MACD Crossover")
                
    for ind in indicators:
        if ind.startswith('SMA_'):
            try:
                period = int(ind.split('_')[1])
                sma = close_prices.rolling(window=period).mean()
                latest_sma = sma.iloc[-1] if not sma.empty else None
                results[ind] = latest_sma
            except ValueError:
                pass
                
    # Determine overall trend based on SMAs if available
    if 'SMA_20' in results and 'SMA_50' in results:
        if results['SMA_20'] is not None and results['SMA_50'] is not None:
            if results['SMA_20'] > results['SMA_50']:
                signals.append("Short-term Bullish Trend (SMA 20 > SMA 50)")
            else:
                signals.append("Short-term Bearish Trend (SMA 20 < SMA 50)")

    # Generate a summary sentiment based on signals
    bullish_count = sum(1 for s in signals if "Bullish" in s or "Oversold" in s)
    bearish_count = sum(1 for s in signals if "Bearish" in s or "Overbought" in s)
    
    if bullish_count > bearish_count:
        summary = "Bullish"
    elif bearish_count > bullish_count:
        summary = "Bearish"
    else:
        summary = "Neutral"

    return {
        'indicator_values': results,
        'signals': signals,
        'summary': summary
    }

def recognize_chart_patterns(price_data: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Identifies common chart patterns in the historical price data.
    
    Args:
        price_data (pd.DataFrame): Historical price data containing 'open', 'high', 'low', 'close'.
        
    Returns:
        List[Dict[str, Any]]: A list of identified patterns with confidence scores and signals.
    """
    patterns = []
    
    if len(price_data) < 20:
        return patterns
        
    # Simple heuristic logic to simulate pattern detection
    recent_data = price_data.tail(20)
    highs = recent_data['high'].values
    lows = recent_data['low'].values
    
    # Heuristic Double Top detection
    if len(highs) >= 10:
        peak1 = np.max(highs[:5])
        peak2 = np.max(highs[-5:])
        if abs(peak1 - peak2) / peak1 < 0.02:  # Peaks are within 2% of each other
            patterns.append({
                'pattern': 'Double Top',
                'confidence': 0.75,
                'signal': 'Bearish',
                'description': 'Two consecutive peaks at approximately the same level indicating potential reversal.'
            })
            
    # Heuristic Double Bottom detection
    if len(lows) >= 10:
        trough1 = np.min(lows[:5])
        trough2 = np.min(lows[-5:])
        if abs(trough1 - trough2) / trough1 < 0.02:
            patterns.append({
                'pattern': 'Double Bottom',
                'confidence': 0.78,
                'signal': 'Bullish',
                'description': 'Two consecutive troughs at approximately the same level indicating potential support.'
            })
            
    return patterns

def predict_price_movements(price_data: pd.DataFrame, timeframe: str = '1d', horizon: int = 5) -> Dict[str, Any]:
    """
    Predicts future price movements based on technical analysis of historical data.
    
    Args:
        price_data (pd.DataFrame): Historical price data.
        timeframe (str): The timeframe of the data (e.g., '1h', '1d').
        horizon (int): Number of periods to predict into the future.
        
    Returns:
        Dict[str, Any]: Prediction results including expected price range, trend direction, and confidence score.
    """
    if 'close' not in price_data.columns:
        raise ValueError("price_data must contain a 'close' column")
        
    current_price = price_data['close'].iloc[-1]
    
    # Use indicator analysis to inform prediction
    analysis = analyze_indicators(price_data)
    summary_signal = analysis.get('summary', 'Neutral')
    
    # Heuristic prediction logic based on summary signal
    if summary_signal == 'Bullish':
        expected_change_pct = 0.015 * horizon  # 1.5% up per period
        trend = 'Upward'
        confidence = 0.65
    elif summary_signal == 'Bearish':
        expected_change_pct = -0.015 * horizon # 1.5% down per period
        trend = 'Downward'
        confidence = 0.65
    else:
        expected_change_pct = 0.0
        trend = 'Sideways'
        confidence = 0.50
        
    target_price = current_price * (1 + expected_change_pct)
    
    # Calculate historical volatility to estimate price range
    returns = price_data['close'].pct_change().dropna()
    volatility = returns.std() * np.sqrt(horizon) if not returns.empty else 0.05
    
    lower_bound = target_price * (1 - volatility)
    upper_bound = target_price * (1 + volatility)
    
    return {
        'current_price': current_price,
        'predicted_target_price': target_price,
        'predicted_trend': trend,
        'timeframe': timeframe,
        'horizon_periods': horizon,
        'confidence_score': confidence,
        'price_range': {
            'lower_bound': lower_bound,
            'upper_bound': upper_bound
        },
        'reasoning': f"Prediction based on {summary_signal} technical indicators over the last {len(price_data)} periods."
    }
===