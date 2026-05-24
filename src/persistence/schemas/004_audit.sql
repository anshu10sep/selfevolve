-- ============================================================
-- SelfEvolve Audit, Observability & Bug Tracking Schema
-- ============================================================

-- Task execution logs: every LLM API call tracked for cost
CREATE TABLE IF NOT EXISTS task_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES agent_registry(id),
    agent_role VARCHAR(50) NOT NULL,
    model_used VARCHAR(50) NOT NULL,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    task_type VARCHAR(50) NOT NULL,
    confidence_score NUMERIC(3, 2),
    escalated BOOLEAN DEFAULT FALSE,
    duration_ms INT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Bug reports: auto-filed from system anomalies
CREATE TABLE IF NOT EXISTS bug_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity VARCHAR(10) NOT NULL
        CHECK (severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')),
    source_agent UUID REFERENCES agent_registry(id),
    category VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
    title VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    stack_trace TEXT,
    reproduction_steps TEXT,
    expected_behavior TEXT,
    actual_behavior TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'WONT_FIX')),
    assigned_to UUID REFERENCES agent_registry(id),
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Immutable audit trail: every trade decision and its full rationale
CREATE TABLE IF NOT EXISTS audit_trail (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES trade_ledger(id),
    ticker VARCHAR(10),
    debate_bull_thesis TEXT,
    debate_bear_thesis TEXT,
    bull_score NUMERIC(4, 2),
    bear_score NUMERIC(4, 2),
    judge_reasoning TEXT,
    execution_order JSONB,
    guardrail_result VARCHAR(20),
    hitl_action VARCHAR(20)
        CHECK (hitl_action IN ('AUTO_PASS', 'HUMAN_APPROVED', 'HUMAN_REJECTED',
                               'TIMEOUT_REJECTED', NULL)),
    langsmith_trace_id VARCHAR(100),
    total_api_cost NUMERIC(10, 6),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- HITL intervention history
CREATE TABLE IF NOT EXISTS hitl_interventions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES trade_ledger(id),
    trigger_reason VARCHAR(100) NOT NULL,
    presented_data JSONB DEFAULT '{}',
    human_action VARCHAR(20) NOT NULL
        CHECK (human_action IN ('APPROVED', 'REJECTED', 'MODIFIED', 'TIMEOUT')),
    rejection_reason VARCHAR(50),
    modification_details JSONB,
    response_time_sec INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- System health log
CREATE TABLE IF NOT EXISTS system_health_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    details JSONB DEFAULT '{}',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_task_logs_agent ON task_execution_logs(agent_role);
CREATE INDEX IF NOT EXISTS idx_task_logs_model ON task_execution_logs(model_used);
CREATE INDEX IF NOT EXISTS idx_task_logs_timestamp ON task_execution_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_bugs_status ON bug_reports(status);
CREATE INDEX IF NOT EXISTS idx_bugs_severity ON bug_reports(severity);
CREATE INDEX IF NOT EXISTS idx_audit_trade ON audit_trail(trade_id);
CREATE INDEX IF NOT EXISTS idx_audit_ticker ON audit_trail(ticker);
CREATE INDEX IF NOT EXISTS idx_hitl_trade ON hitl_interventions(trade_id);
CREATE INDEX IF NOT EXISTS idx_health_component ON system_health_log(component);
CREATE INDEX IF NOT EXISTS idx_health_timestamp ON system_health_log(timestamp);
