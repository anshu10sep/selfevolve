"""
Alpaca Broker Client

Wrapper around the Alpaca API for account management, market data,
and order operations. Handles fractional shares, bracket orders,
and rate limiting.
"""

from __future__ import annotations

from typing import Any, Optional
from datetime import datetime, timezone

import httpx
import structlog

from config.settings import get_settings
from core.models.portfolio import PortfolioState, Position, TradeSide, TradeIntent

logger = structlog.get_logger(component="alpaca_client")


class AlpacaClient:
    """
    Alpaca API client for the SelfEvolve trading system.
    
    Handles:
    - Account status and health verification
    - Market data retrieval
    - Fractional order submission (notional-based)
    - Bracket/OTOCO order types
    - Fill reconciliation via REST polling
    """

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.alpaca_base_url
        self.data_url = settings.alpaca_data_url
        self.headers = {
            "APCA-API-KEY-ID": settings.alpaca_api_key,
            "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
            "Content-Type": "application/json",
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Account Operations ─────────────────────────────────────────

    async def get_account(self) -> dict[str, Any]:
        """
        Get account information from Alpaca.
        
        Used for JIT ledger validation before every order.
        """
        client = await self._get_client()
        response = await client.get(f"{self.base_url}/v2/account")
        response.raise_for_status()
        return response.json()

    async def verify_cash_account(self) -> bool:
        """
        Verify the account is a CASH account (not MARGIN).
        
        The system refuses to start if a margin account is detected.
        """
        account = await self.get_account()
        account_type = account.get("account_type", "").upper()
        if account_type != "CASH" and not account.get("is_paper", True):
            logger.critical(
                "margin_account_detected",
                account_type=account_type,
            )
            return False
        return True

    async def get_portfolio_state(self) -> PortfolioState:
        """Build a PortfolioState from the live Alpaca account."""
        account = await self.get_account()
        positions = await self.get_positions()

        position_map = {}
        for pos in positions:
            ticker = pos.get("symbol", "")
            position_map[ticker] = Position(
                ticker=ticker,
                quantity=float(pos.get("qty", 0)),
                avg_entry_price=float(pos.get("avg_entry_price", 0)),
                current_price=float(pos.get("current_price", 0)),
                market_value=float(pos.get("market_value", 0)),
                side=TradeSide.BUY if pos.get("side") == "long" else TradeSide.SELL,
            )

        return PortfolioState(
            total_equity=float(account.get("equity", 0)),
            settled_cash=float(account.get("cash", 0)),
            unsettled_cash=float(account.get("pending_transfer_in", 0)),
            buying_power=float(account.get("buying_power", 0)),
            positions=position_map,
            updated_at=datetime.now(timezone.utc),
        )

    # ── Position Operations ────────────────────────────────────────

    async def get_positions(self) -> list[dict]:
        """Get all open positions."""
        client = await self._get_client()
        response = await client.get(f"{self.base_url}/v2/positions")
        response.raise_for_status()
        return response.json()

    # ── Order Operations ───────────────────────────────────────────

    async def submit_notional_order(
        self, trade_intent: TradeIntent
    ) -> dict[str, Any]:
        """
        Submit a notional (dollar-amount) order for fractional shares.
        
        Uses the 'notional' parameter instead of 'qty' to enable
        precise dollar-amount allocation with fractional shares.
        """
        order_data = {
            "symbol": trade_intent.ticker,
            "notional": str(trade_intent.notional),
            "side": trade_intent.side.value.lower(),
            "type": "market",
            "time_in_force": "day",
            "client_order_id": trade_intent.client_order_id,
        }

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v2/orders",
            json=order_data,
        )
        response.raise_for_status()

        result = response.json()
        logger.info(
            "order_submitted",
            ticker=trade_intent.ticker,
            side=trade_intent.side.value,
            notional=trade_intent.notional,
            client_order_id=trade_intent.client_order_id,
            order_id=result.get("id"),
        )
        return result

    async def submit_bracket_order(
        self, trade_intent: TradeIntent
    ) -> dict[str, Any]:
        """
        Submit a bracket (OTOCO) order: entry + stop loss + take profit.
        
        All three legs are submitted atomically to Alpaca's servers,
        eliminating the risk of a crash leaving a position unhedged.
        """
        if not trade_intent.stop_loss_price or not trade_intent.take_profit_price:
            # Fall back to simple notional order if no SL/TP
            return await self.submit_notional_order(trade_intent)

        order_data = {
            "symbol": trade_intent.ticker,
            "notional": str(trade_intent.notional),
            "side": trade_intent.side.value.lower(),
            "type": "market",
            "time_in_force": "day",
            "client_order_id": trade_intent.client_order_id,
            "order_class": "bracket",
            "stop_loss": {
                "stop_price": str(trade_intent.stop_loss_price),
            },
            "take_profit": {
                "limit_price": str(trade_intent.take_profit_price),
            },
        }

        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/v2/orders",
            json=order_data,
        )
        response.raise_for_status()

        result = response.json()
        logger.info(
            "bracket_order_submitted",
            ticker=trade_intent.ticker,
            notional=trade_intent.notional,
            stop_loss=trade_intent.stop_loss_price,
            take_profit=trade_intent.take_profit_price,
            order_id=result.get("id"),
        )
        return result

    async def cancel_all_orders(self) -> list[dict]:
        """Cancel all open orders. Used by HCF protocol."""
        client = await self._get_client()
        response = await client.delete(f"{self.base_url}/v2/orders")
        response.raise_for_status()
        logger.warning("all_orders_cancelled")
        return response.json()

    async def get_order_by_client_id(self, client_order_id: str) -> Optional[dict]:
        """Get order by client order ID for idempotent recovery."""
        client = await self._get_client()
        try:
            response = await client.get(
                f"{self.base_url}/v2/orders:by_client_order_id",
                params={"client_order_id": client_order_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_recent_activities(
        self, activity_type: str = "FILL", limit: int = 50
    ) -> list[dict]:
        """Get recent account activities for settlement tracking."""
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/v2/account/activities/{activity_type}",
            params={"page_size": limit},
        )
        response.raise_for_status()
        return response.json()

    # ── Market Data ────────────────────────────────────────────────

    async def get_latest_quote(self, ticker: str) -> dict[str, Any]:
        """Get the latest quote for a ticker."""
        client = await self._get_client()
        response = await client.get(
            f"{self.data_url}/v2/stocks/{ticker}/quotes/latest",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def get_bars(
        self,
        ticker: str,
        timeframe: str = "1Day",
        limit: int = 30,
    ) -> list[dict]:
        """Get historical price bars for ATR calculation."""
        client = await self._get_client()
        response = await client.get(
            f"{self.data_url}/v2/stocks/{ticker}/bars",
            headers=self.headers,
            params={
                "timeframe": timeframe,
                "limit": limit,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("bars", [])
