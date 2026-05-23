# Technical Analyst Agent

## Purpose
The Technical Analyst is a highly deterministic Deep Research Sub-Agent tasked with evaluating mathematical price action to identify immediate support/resistance thresholds and optimize exact entry/exit vectors.

## Primary Inputs & Data Sources
- **Historical Market Price Data**: OHLCV (Open, High, Low, Close, Volume) candlestick arrays.
- **Order Book Depth**: Level 2 data to identify liquidity walls and bid-ask spreads.
- **Technical Indicators**: Relative Strength Index (RSI), Moving Average Convergence Divergence (MACD), Bollinger Bands, VWAP.

## Operational Execution
While the Fundamental Agent assesses *what* to buy, the Technical Analyst assesses *when* to buy. It calculates intraday volatility coefficients and identifies short-term trend divergences that are highly relevant to day-trading and swing-trading strategies under micro-capital constraints.

## Structured Output
The agent delivers technical trend assessments, precise probability mapping for breakouts or breakdowns, and critically, defines exact price levels for stop-loss and take-profit mechanisms to protect the initial $100 capital base.
