"""
Strategy Backtester

Tests trading strategies against historical Alpaca data.
Calculates Sharpe ratio, max drawdown, win rate, and other
performance metrics.
"""

from __future__ import annotations

import math
from typing import Optional

import structlog

from integrations.market_data import MarketDataClient

logger = structlog.get_logger(component="backtester")


class StrategyBacktester:
    """Backtests trading strategies on historical data."""

    def __init__(self, market_data: Optional[MarketDataClient] = None):
        self.market_data = market_data or MarketDataClient()

    async def backtest_momentum(
        self,
        ticker: str,
        lookback_days: int = 60,
        hold_days: int = 5,
        entry_threshold: float = 0.02,
    ) -> dict:
        """
        Momentum strategy: Buy when 5-day return > entry_threshold,
        sell after hold_days.
        """
        bars = await self.market_data.get_bars(ticker, timeframe="1Day", limit=lookback_days)
        if len(bars) < 10:
            return {"error": "Not enough data", "ticker": ticker}

        trades = []
        i = 5  # Need 5 bars for lookback
        while i < len(bars) - hold_days:
            # Entry signal: 5-day momentum > threshold
            five_day_return = (bars[i]["close"] - bars[i - 5]["close"]) / bars[i - 5]["close"]

            if five_day_return > entry_threshold:
                entry_price = bars[i]["close"]
                exit_price = bars[min(i + hold_days, len(bars) - 1)]["close"]
                pnl_pct = (exit_price - entry_price) / entry_price * 100

                trades.append({
                    "entry_date": bars[i]["timestamp"][:10],
                    "exit_date": bars[min(i + hold_days, len(bars) - 1)]["timestamp"][:10],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "win": pnl_pct > 0,
                })
                i += hold_days  # Skip ahead past the hold period
            else:
                i += 1

        return self._compute_stats(ticker, "Momentum", trades, bars)

    async def backtest_mean_reversion(
        self,
        ticker: str,
        lookback_days: int = 60,
        rsi_period: int = 14,
        rsi_buy: float = 30.0,
        rsi_sell: float = 70.0,
    ) -> dict:
        """
        Mean reversion: Buy when RSI < rsi_buy, sell when RSI > rsi_sell.
        """
        bars = await self.market_data.get_bars(ticker, timeframe="1Day", limit=lookback_days)
        if len(bars) < rsi_period + 5:
            return {"error": "Not enough data", "ticker": ticker}

        # Calculate RSI
        rsi_values = self._calculate_rsi(bars, rsi_period)

        trades = []
        in_position = False
        entry_price = 0.0
        entry_date = ""

        for i in range(len(rsi_values)):
            bar_idx = i + rsi_period
            if bar_idx >= len(bars):
                break

            rsi = rsi_values[i]

            if not in_position and rsi < rsi_buy:
                # Buy signal
                in_position = True
                entry_price = bars[bar_idx]["close"]
                entry_date = bars[bar_idx]["timestamp"][:10]

            elif in_position and rsi > rsi_sell:
                # Sell signal
                exit_price = bars[bar_idx]["close"]
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": bars[bar_idx]["timestamp"][:10],
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl_pct": pnl_pct,
                    "win": pnl_pct > 0,
                })
                in_position = False

        return self._compute_stats(ticker, "Mean Reversion (RSI)", trades, bars)

    async def compare_strategies(self, ticker: str, lookback_days: int = 60) -> dict:
        """Run both strategies and compare results."""
        momentum = await self.backtest_momentum(ticker, lookback_days)
        mean_rev = await self.backtest_mean_reversion(ticker, lookback_days)

        # Determine winner
        m_sharpe = momentum.get("sharpe_ratio", -999)
        r_sharpe = mean_rev.get("sharpe_ratio", -999)

        winner = "Momentum" if m_sharpe > r_sharpe else "Mean Reversion"

        return {
            "ticker": ticker,
            "lookback_days": lookback_days,
            "momentum": momentum,
            "mean_reversion": mean_rev,
            "recommended": winner,
            "reasoning": f"{winner} has a higher Sharpe ratio ({max(m_sharpe, r_sharpe):.2f} vs {min(m_sharpe, r_sharpe):.2f})",
        }

    # ── Internal Helpers ──────────────────────────────────────

    def _calculate_rsi(self, bars: list[dict], period: int = 14) -> list[float]:
        """Calculate RSI for a series of bars."""
        closes = [b["close"] for b in bars]
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        rsi_values = []
        gains = [max(0, d) for d in deltas[:period]]
        losses = [abs(min(0, d)) for d in deltas[:period]]

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        for i in range(period, len(deltas)):
            if avg_loss == 0:
                rsi_values.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))

            delta = deltas[i]
            avg_gain = (avg_gain * (period - 1) + max(0, delta)) / period
            avg_loss = (avg_loss * (period - 1) + abs(min(0, delta))) / period

        return rsi_values

    def _compute_stats(
        self,
        ticker: str,
        strategy_name: str,
        trades: list[dict],
        bars: list[dict],
    ) -> dict:
        """Compute performance statistics from a list of trades."""
        if not trades:
            return {
                "ticker": ticker,
                "strategy": strategy_name,
                "num_trades": 0,
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "trades": [],
            }

        pnls = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_return = sum(pnls)
        avg_return = total_return / len(pnls)
        std_return = math.sqrt(sum((p - avg_return) ** 2 for p in pnls) / max(1, len(pnls) - 1)) if len(pnls) > 1 else 0

        # Annualized Sharpe (assume ~252 trading days, average hold ~5 days)
        trades_per_year = 252 / max(1, len(bars) / max(1, len(trades)))
        sharpe = (avg_return / std_return * math.sqrt(trades_per_year)) if std_return > 0 else 0

        # Max drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            cumulative += p
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        return {
            "ticker": ticker,
            "strategy": strategy_name,
            "num_trades": len(trades),
            "total_return": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "win_rate": round(len(wins) / len(pnls) * 100, 1),
            "avg_win": round(sum(wins) / max(1, len(wins)), 2),
            "avg_loss": round(sum(losses) / max(1, len(losses)), 2),
            "trades": trades,
        }
