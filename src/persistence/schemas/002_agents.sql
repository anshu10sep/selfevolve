-- ============================================================
-- SelfEvolve Agent Registry & Trust Schema
-- ============================================================

-- Agent registry: every agent in the hierarchy
CREATE TABLE IF NOT EXISTS agent_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name VARCHAR(100) UNIQUE NOT NULL,
    agent_role VARCHAR(50) NOT NULL,
    agent_type VARCHAR(20) NOT NULL
        CHECK (agent_type IN ('EXECUTIVE', 'MANAGER', 'ANALYST', 'SPECIALIST')),
    identity_core TEXT NOT NULL,
    strategic_nuance TEXT DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'IDLE', 'EVOLVING', 'RETIRED', 'ERROR')),
    parent_agent_id UUID REFERENCES agent_registry(id),
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent trust weights: transparent, database-stored trust scores
CREATE TABLE IF NOT EXISTS agent_trust_weights (
    agent_id UUID PRIMARY KEY REFERENCES agent_registry(id),
    current_weight NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    historical_brier_score NUMERIC(5, 4) DEFAULT 0.5000,
    total_predictions INT NOT NULL DEFAULT 0,
    correct_predictions INT NOT NULL DEFAULT 0,
    consecutive_failures INT NOT NULL DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Agent prompt version history
CREATE TABLE IF NOT EXISTS agent_prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_registry(id),
    version_number INT NOT NULL,
    prompt_text TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    performance_sharpe NUMERIC(8, 4),
    performance_win_rate NUMERIC(5, 4),
    performance_brier NUMERIC(5, 4),
    a_b_test_result VARCHAR(20)
        CHECK (a_b_test_result IN ('PENDING', 'PROMOTED', 'ROLLED_BACK', 'INCONCLUSIVE')),
    trade_count INT DEFAULT 0,
    p_value NUMERIC(6, 4),
    UNIQUE(agent_id, version_number)
);

-- Agent activity log: every action taken by every agent
CREATE TABLE IF NOT EXISTS agent_activity_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_registry(id),
    action_type VARCHAR(50) NOT NULL,
    action_details JSONB DEFAULT '{}',
    model_used VARCHAR(50),
    tokens_used INT DEFAULT 0,
    cost_usd NUMERIC(10, 6) DEFAULT 0,
    duration_ms INT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_agent_role ON agent_registry(agent_role);
CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_registry(status);
CREATE INDEX IF NOT EXISTS idx_agent_parent ON agent_registry(parent_agent_id);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_agent ON agent_prompt_versions(agent_id);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_active ON agent_prompt_versions(is_active);
CREATE INDEX IF NOT EXISTS idx_activity_agent ON agent_activity_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON agent_activity_log(timestamp);
