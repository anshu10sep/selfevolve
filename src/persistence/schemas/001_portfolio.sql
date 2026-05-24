-- ============================================================
-- SelfEvolve Portfolio & Trading Schema
-- Auto-loaded by PostgreSQL on first container startup
-- ============================================================

-- Portfolio state snapshot
CREATE TABLE IF NOT EXISTS portfolio_state (
    id SERIAL PRIMARY KEY,
    total_equity NUMERIC(12, 4) NOT NULL DEFAULT 100.0,
    settled_cash NUMERIC(12, 4) NOT NULL DEFAULT 100.0,
    unsettled_cash NUMERIC(12, 4) NOT NULL DEFAULT 0.0,
    buying_power NUMERIC(12, 4) NOT NULL DEFAULT 100.0,
    high_water_mark NUMERIC(12, 4) NOT NULL DEFAULT 100.0,
    daily_pnl NUMERIC(12, 4) NOT NULL DEFAULT 0.0,
    total_api_cost_today NUMERIC(10, 6) NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Trade ledger: every trade that flows through the system
CREATE TABLE IF NOT EXISTS trade_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(10) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity NUMERIC(12, 6) NOT NULL,
    notional NUMERIC(12, 4) NOT NULL,
    entry_price NUMERIC(12, 4),
    exit_price NUMERIC(12, 4),
    realized_pnl NUMERIC(12, 4),
    client_order_id VARCHAR(64) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'SUBMITTED', 'FILLED', 'PARTIALLY_FILLED',
                          'CANCELLED', 'REJECTED', 'EXPIRED')),
    conviction_score NUMERIC(4, 2),
    reasoning TEXT,
    entry_time TIMESTAMP WITH TIME ZONE,
    exit_time TIMESTAMP WITH TIME ZONE,
    settlement_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Capital tranche lifecycle tracking
CREATE TABLE IF NOT EXISTS tranche_state (
    id SERIAL PRIMARY KEY,
    tranche_index INT NOT NULL UNIQUE,
    amount NUMERIC(12, 4) NOT NULL DEFAULT 10.0,
    status VARCHAR(20) NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN ('AVAILABLE', 'LOCKED', 'SETTLING')),
    locked_trade_id UUID REFERENCES trade_ledger(id),
    locked_at TIMESTAMP WITH TIME ZONE,
    settling_until TIMESTAMP WITH TIME ZONE
);

-- Good Faith Violation tracking (max 2 per 12 months)
CREATE TABLE IF NOT EXISTS gfv_strike_count (
    id SERIAL PRIMARY KEY,
    strike_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    trade_id UUID REFERENCES trade_ledger(id),
    reason TEXT NOT NULL,
    strike_number INT NOT NULL,
    was_intentional BOOLEAN DEFAULT FALSE
);

-- Slippage tracking for fill quality analysis
CREATE TABLE IF NOT EXISTS slippage_tracking (
    trade_id UUID PRIMARY KEY REFERENCES trade_ledger(id),
    ticker VARCHAR(10) NOT NULL,
    intended_price NUMERIC(12, 4) NOT NULL,
    fill_price NUMERIC(12, 4) NOT NULL,
    slippage_pct NUMERIC(8, 6) NOT NULL,
    daily_volume NUMERIC(16, 2),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_trade_ledger_ticker ON trade_ledger(ticker);
CREATE INDEX IF NOT EXISTS idx_trade_ledger_status ON trade_ledger(status);
CREATE INDEX IF NOT EXISTS idx_trade_ledger_created ON trade_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_trade_ledger_client_order ON trade_ledger(client_order_id);
CREATE INDEX IF NOT EXISTS idx_slippage_ticker ON slippage_tracking(ticker);
