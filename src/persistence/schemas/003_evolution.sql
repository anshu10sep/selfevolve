-- ============================================================
-- SelfEvolve Evolution & Reflexion Schema
-- ============================================================

-- Reflexion journal: linguistic post-mortems from the Reflexion framework
CREATE TABLE IF NOT EXISTS reflexion_journal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_registry(id),
    trade_id UUID REFERENCES trade_ledger(id),
    prediction_probability NUMERIC(5, 4),
    actual_outcome INT CHECK (actual_outcome IN (0, 1)),
    brier_score NUMERIC(5, 4),
    linguistic_postmortem TEXT,
    market_context JSONB DEFAULT '{}',
    data_snapshot JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Shadow crew A/B test results
CREATE TABLE IF NOT EXISTS shadow_crew_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_registry(id),
    production_version INT NOT NULL,
    shadow_version INT NOT NULL,
    production_sharpe NUMERIC(8, 4),
    shadow_sharpe NUMERIC(8, 4),
    production_win_rate NUMERIC(5, 4),
    shadow_win_rate NUMERIC(5, 4),
    trade_count INT NOT NULL DEFAULT 0,
    p_value NUMERIC(6, 4),
    z_score NUMERIC(6, 4),
    promoted BOOLEAN DEFAULT FALSE,
    evaluation_notes TEXT,
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Evolution events: what changed, when, why
CREATE TABLE IF NOT EXISTS evolution_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL
        CHECK (event_type IN ('PROMPT_UPDATE', 'TRUST_DECAY', 'AGENT_SPAWN',
                              'AGENT_RETIRE', 'PARAMETER_UPDATE', 'STRATEGY_SHIFT',
                              'RULE_CONSOLIDATION', 'SHADOW_PROMOTION')),
    agent_id UUID REFERENCES agent_registry(id),
    old_version INT,
    new_version INT,
    change_description TEXT NOT NULL,
    statistical_significance NUMERIC(6, 4),
    brier_before NUMERIC(5, 4),
    brier_after NUMERIC(5, 4),
    sharpe_before NUMERIC(8, 4),
    sharpe_after NUMERIC(8, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Rolling Brier score history per agent
CREATE TABLE IF NOT EXISTS brier_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_registry(id),
    window_start TIMESTAMP WITH TIME ZONE NOT NULL,
    window_end TIMESTAMP WITH TIME ZONE NOT NULL,
    brier_score NUMERIC(5, 4) NOT NULL,
    trade_count INT NOT NULL,
    predictions_data JSONB DEFAULT '[]',
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_reflexion_agent ON reflexion_journal(agent_id);
CREATE INDEX IF NOT EXISTS idx_reflexion_trade ON reflexion_journal(trade_id);
CREATE INDEX IF NOT EXISTS idx_reflexion_created ON reflexion_journal(created_at);
CREATE INDEX IF NOT EXISTS idx_shadow_agent ON shadow_crew_results(agent_id);
CREATE INDEX IF NOT EXISTS idx_evolution_agent ON evolution_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_evolution_type ON evolution_events(event_type);
CREATE INDEX IF NOT EXISTS idx_brier_agent ON brier_score_history(agent_id);
