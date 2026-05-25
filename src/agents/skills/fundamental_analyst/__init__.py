try:
    from .yfinance_fundamentals import analyze_financial_statements
except ImportError:
    analyze_financial_statements = None  # yfinance not installed

__all__ = ["analyze_financial_statements"]