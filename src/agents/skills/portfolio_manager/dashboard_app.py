"""
Standalone Streamlit Dashboard to display the Top 20 Selected Stocks for Trading.
Run this file using: `streamlit run agents/skills/portfolio_manager/dashboard_app.py`
"""

import streamlit as st
import sys
import os

# Ensure the skill can be imported if run directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from top_stocks_widget import render_streamlit_top_stocks

def main():
    st.set_page_config(page_title="SelfEvolve Trading Dashboard", layout="wide")
    st.title("📈 SelfEvolve Autonomous Trading System")
    
    # Mock data representing the top 20 selected stocks for trading
    # In production, this would be fetched via `agents.skills.database.fetch_top_stocks`
    mock_top_stocks = [
        {"symbol": "AAPL", "price": 175.50, "change_pct": 1.2, "volume": 55000000, "signal": "STRONG BUY"},
        {"symbol": "MSFT", "price": 330.20, "change_pct": 0.8, "volume": 25000000, "signal": "BUY"},
        {"symbol": "NVDA", "price": 450.10, "change_pct": -2.1, "volume": 40000000, "signal": "BUY"},
        {"symbol": "TSLA", "price": 240.30, "change_pct": 3.5, "volume": 120000000, "signal": "STRONG BUY"},
        {"symbol": "AMZN", "price": 135.40, "change_pct": 0.5, "volume": 45000000, "signal": "BUY"},
        {"symbol": "META", "price": 300.10, "change_pct": 1.5, "volume": 20000000, "signal": "BUY"},
        {"symbol": "GOOGL", "price": 130.50, "change_pct": 0.2, "volume": 22000000, "signal": "HOLD"},
        {"symbol": "BRK.B", "price": 360.20, "change_pct": 0.1, "volume": 3000000, "signal": "BUY"},
        {"symbol": "UNH", "price": 490.30, "change_pct": -0.5, "volume": 2500000, "signal": "HOLD"},
        {"symbol": "JNJ", "price": 160.40, "change_pct": 0.3, "volume": 5000000, "signal": "BUY"},
        {"symbol": "JPM", "price": 145.20, "change_pct": 1.1, "volume": 8000000, "signal": "BUY"},
        {"symbol": "V", "price": 240.50, "change_pct": 0.6, "volume": 4000000, "signal": "BUY"},
        {"symbol": "PG", "price": 150.30, "change_pct": -0.2, "volume": 6000000, "signal": "HOLD"},
        {"symbol": "MA", "price": 400.10, "change_pct": 0.7, "volume": 2000000, "signal": "BUY"},
        {"symbol": "HD", "price": 320.40, "change_pct": -1.2, "volume": 3500000, "signal": "HOLD"},
        {"symbol": "CVX", "price": 165.20, "change_pct": 2.1, "volume": 7000000, "signal": "STRONG BUY"},
        {"symbol": "ABBV", "price": 145.60, "change_pct": 0.4, "volume": 4500000, "signal": "BUY"},
        {"symbol": "LLY", "price": 550.30, "change_pct": 1.8, "volume": 2500000, "signal": "STRONG BUY"},
        {"symbol": "PEP", "price": 175.20, "change_pct": -0.3, "volume": 4000000, "signal": "HOLD"},
        {"symbol": "KO", "price": 58.40, "change_pct": 0.1, "volume": 10000000, "signal": "BUY"},
    ]
    
    st.sidebar.header("Dashboard Controls")
    if st.sidebar.button("Refresh Data"):
        st.toast("Data refreshed successfully!")
        
    # Render the top 20 stocks widget
    render_streamlit_top_stocks(mock_top_stocks)

if __name__ == "__main__":
    main()