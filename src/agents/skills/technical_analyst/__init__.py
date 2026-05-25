try:
    from .fetch_and_analyze import analyze_technical_indicators
except ImportError:
    analyze_technical_indicators = None  # pandas_ta not installed

__all__ = ["analyze_technical_indicators"]