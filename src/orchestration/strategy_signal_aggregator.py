"""
Strategy Signal Aggregator

Runs all registered strategy agents in parallel for a given ticker,
aggregates their signals using trust-weighted scoring, and records
predictions for Brier scoring.

This bridges the gap between the strategy agent framework (which has
beautiful self-evolution infrastructure) and the actual trading flow
(which previously only used LLM-based analysts).

Integration points:
  - Called from parallel_research_node in trading_dag.py
  - Predictions feed into strategy_evolution_engine via Brier scores
  - Trust weights flow from strategy evolution back into aggregation
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from agents.strategies.strategy_base import StrategySignal, SignalType

logger = structlog.get_logger(component="strategy_aggregator")


async def aggregate_strategy_signals(
    ticker: str,
    market_data: dict[str, Any],
    record_predictions: bool = True,
) -> dict[str, Any]:
    """Run all registered strategy agents and aggregate their signals.

    Args:
        ticker: Stock/crypto ticker to analyze
        market_data: Pre-fetched market data (bars, quotes, etc.)
        record_predictions: If True, records predictions for Brier scoring

    Returns:
        Dict with:
        - consensus_action: BUY/SELL/HOLD
        - consensus_score: -1.0 to 1.0 (weighted average)
        - consensus_confidence: 0.0 to 1.0
        - individual_signals: list of per-strategy results
        - strategies_evaluated: count
    """
    from agents.strategies.strategy_evolution import strategy_evolution_engine

    strategies = strategy_evolution_engine._strategies
    if not strategies:
        return _empty_result(ticker)

    # Run all strategies in parallel
    tasks = []
    strategy_names = []
    for name, strategy in strategies.items():
        tasks.append(_run_strategy_safe(name, strategy, ticker, market_data))
        strategy_names.append(name)

    results = await asyncio.gather(*tasks)

    # Build signal list
    individual_signals = []
    for name, result in zip(strategy_names, results):
        if result is not None:
            individual_signals.append(result)

    if not individual_signals:
        return _empty_result(ticker)

    # Aggregate using trust-weighted scoring
    total_weight = 0.0
    weighted_score = 0.0
    weighted_confidence = 0.0
    buy_count = 0
    sell_count = 0
    hold_count = 0

    for sig in individual_signals:
        weight = sig.get("trust_weight", 1.0)
        score = sig.get("score", 0.0)  # -1 to 1
        conf = sig.get("confidence", 0.0)

        weighted_score += score * weight
        weighted_confidence += conf * weight
        total_weight += weight

        action = sig.get("action", "HOLD")
        if action == "BUY":
            buy_count += 1
        elif action == "SELL":
            sell_count += 1
        else:
            hold_count += 1

    consensus_score = weighted_score / total_weight if total_weight > 0 else 0.0
    consensus_confidence = weighted_confidence / total_weight if total_weight > 0 else 0.0

    # Determine consensus action
    if consensus_score > 0.2 and buy_count > sell_count:
        consensus_action = "BUY"
    elif consensus_score < -0.2 and sell_count > buy_count:
        consensus_action = "SELL"
    else:
        consensus_action = "HOLD"

    # Record predictions for strategies that generated BUY/SELL signals
    if record_predictions:
        await _record_strategy_predictions(
            ticker, individual_signals, consensus_action
        )

    result = {
        "ticker": ticker,
        "consensus_action": consensus_action,
        "consensus_score": round(consensus_score, 4),
        "consensus_confidence": round(consensus_confidence, 4),
        "strategies_evaluated": len(individual_signals),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "hold_count": hold_count,
        "individual_signals": individual_signals,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "strategy_consensus",
        ticker=ticker,
        action=consensus_action,
        score=f"{consensus_score:.3f}",
        confidence=f"{consensus_confidence:.3f}",
        strategies=len(individual_signals),
        buys=buy_count,
        sells=sell_count,
    )

    return result


async def _run_strategy_safe(
    name: str,
    strategy,
    ticker: str,
    market_data: dict,
) -> Optional[dict]:
    """Run a single strategy agent safely (catches all exceptions).

    Returns a dict with the strategy's signal, or None on failure.
    """
    try:
        signals = await strategy.generate_signals(
            tickers=[ticker],
            market_data=market_data,
        )

        if not signals:
            return {
                "strategy_name": name,
                "action": "HOLD",
                "score": 0.0,
                "confidence": 0.0,
                "trust_weight": strategy.trust_weight,
                "rationale": "No signal generated",
            }

        # Use the first signal for this ticker
        signal = signals[0]

        # Convert signal type to score (-1 to 1)
        if signal.signal_type == SignalType.BUY:
            score = signal.strength
        elif signal.signal_type == SignalType.SELL:
            score = -signal.strength
        else:
            score = 0.0

        return {
            "strategy_name": name,
            "action": signal.signal_type.value,
            "score": round(score, 4),
            "confidence": round(signal.confidence, 4),
            "strength": round(signal.strength, 4),
            "trust_weight": strategy.trust_weight,
            "rationale": signal.rationale[:200],
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss_price,
            "take_profit": signal.take_profit_price,
            "strategy_version": signal.strategy_version,
        }

    except Exception as e:
        logger.warning(
            "strategy_signal_failed",
            strategy=name,
            ticker=ticker,
            error=str(e),
        )
        return None


async def _record_strategy_predictions(
    ticker: str,
    signals: list[dict],
    consensus_action: str,
) -> None:
    """Record strategy predictions for Brier scoring.

    Each strategy that generates a BUY or SELL signal gets a prediction
    recorded. The trade_id is the consensus trade_id (ticker + timestamp)
    so all strategy predictions resolve together when the trade closes.
    """
    try:
        from evolution.prediction_tracker import prediction_tracker

        # Only record if there's a consensus BUY
        if consensus_action not in ("BUY", "SELL"):
            return

        trade_id = f"strat_{ticker}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}"

        for sig in signals:
            action = sig.get("action", "HOLD")
            if action in ("BUY", "SELL"):
                # For BUY signals, predicted probability = confidence
                # For SELL signals, predicted probability = 1 - confidence
                # (inverse — predicting the trade will be unprofitable)
                prob = sig.get("confidence", 0.5)
                if action == "SELL" and consensus_action == "BUY":
                    prob = 1 - prob  # Strategy disagrees with consensus

                strategy_role = f"STRATEGY_{sig['strategy_name'].upper()}"
                try:
                    prediction_tracker.record_prediction(
                        agent_role=strategy_role,
                        trade_id=trade_id,
                        ticker=ticker,
                        predicted_probability=prob,
                        confidence=sig.get("confidence", 0.5),
                    )
                except Exception as e:
                    logger.debug(
                        "strategy_prediction_record_failed",
                        strategy=sig["strategy_name"],
                        error=str(e),
                    )

    except Exception as e:
        logger.warning("strategy_prediction_recording_failed", error=str(e))


def format_for_judge(strategy_result: dict) -> str:
    """Format strategy consensus for inclusion in the Judge's prompt.

    Returns a human-readable summary the Judge can consider
    alongside the analyst scores and debate.
    """
    if not strategy_result or strategy_result.get("strategies_evaluated", 0) == 0:
        return "Strategy Signals: No strategy agents available"

    lines = [
        f"Strategy Consensus: {strategy_result['consensus_action']} "
        f"(score: {strategy_result['consensus_score']:.2f}, "
        f"confidence: {strategy_result['consensus_confidence']:.0%})",
        f"Strategies: {strategy_result['buy_count']} BUY, "
        f"{strategy_result['sell_count']} SELL, "
        f"{strategy_result['hold_count']} HOLD",
    ]

    # Add top signals
    signals = strategy_result.get("individual_signals", [])
    actionable = [s for s in signals if s.get("action") in ("BUY", "SELL")]
    for sig in actionable[:3]:
        lines.append(
            f"  - {sig['strategy_name']}: {sig['action']} "
            f"(strength: {sig.get('strength', 0):.2f}, "
            f"trust: {sig.get('trust_weight', 1.0):.2f}) — "
            f"{sig.get('rationale', '')[:80]}"
        )

    return "\n".join(lines)


def _empty_result(ticker: str) -> dict[str, Any]:
    """Return an empty result when no strategies are available."""
    return {
        "ticker": ticker,
        "consensus_action": "HOLD",
        "consensus_score": 0.0,
        "consensus_confidence": 0.0,
        "strategies_evaluated": 0,
        "buy_count": 0,
        "sell_count": 0,
        "hold_count": 0,
        "individual_signals": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
