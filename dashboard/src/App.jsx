import React, { useState, useEffect, useRef } from 'react';
import {
  Activity, Server, Cpu, Layers, GitPullRequest, Settings, TerminalSquare,
  AlertTriangle, X, Play, Square, RefreshCw, Search, DollarSign, TrendingUp,
  TrendingDown, Pause, Zap, Shield, BarChart3, Wifi, WifiOff
} from 'lucide-react';
import { ReactFlow, Controls, Background } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './index.css';
import {
  fetchSystemStatus, fetchAgents, fetchAgentDetail, fetchPortfolio, fetchBugSummary,
  fetchBugs, fetchBugDetail, fetchCosts, fetchWatchdog, fetchVelocity, fetchEvolution,
  fetchTrades, forceEvolution, forceAudit, pauseSystem, resumeSystem, connectWebSocket,
} from './api.js';

// ═══════════════════════════════════════════════════════════════════
// HELPER: Format currency
// ═══════════════════════════════════════════════════════════════════
function fmt(val, decimals = 2) {
  if (val == null || isNaN(val)) return '-';
  return Number(val).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtUSD(val) {
  if (val == null || isNaN(val)) return '$-';
  const prefix = val < 0 ? '-$' : '$';
  return prefix + fmt(Math.abs(val));
}

// ═══════════════════════════════════════════════════════════════════
// HELPER: Format timestamps in PST (Pacific Time)
// ═══════════════════════════════════════════════════════════════════
const PST_TIMEZONE = 'America/Los_Angeles';

function formatPST(isoString, options = {}) {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    const defaults = { timeZone: PST_TIMEZONE };
    return d.toLocaleString('en-US', { ...defaults, ...options });
  } catch { return isoString; }
}

function formatDatePST(isoString) {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', {
      timeZone: PST_TIMEZONE,
      weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
    }) + ' at ' + d.toLocaleTimeString('en-US', {
      timeZone: PST_TIMEZONE,
      hour: '2-digit', minute: '2-digit',
    }) + ' PST';
  } catch { return isoString; }
}

function formatTimePST(isoString) {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString('en-US', {
      timeZone: PST_TIMEZONE,
      hour: '2-digit', minute: '2-digit', second: '2-digit',
      hour12: false,
    });
  } catch { return isoString; }
}

function pnlClass(val) {
  if (val == null) return '';
  return val >= 0 ? 'positive' : 'negative';
}

// ═══════════════════════════════════════════════════════════════════
// SIDEBAR
// ═══════════════════════════════════════════════════════════════════
function Sidebar({ activeTab, setActiveTab, systemStatus, wsConnected }) {
  const navItems = [
    { id: 'overview', icon: <Layers />, label: 'Overview' },
    { id: 'agents', icon: <Cpu />, label: 'Agent Ecosystem' },
    { id: 'portfolio', icon: <DollarSign />, label: 'Portfolio & P&L' },
    { id: 'bugs', icon: <AlertTriangle />, label: 'Bug Pipeline' },
    { id: 'watchdog', icon: <Server />, label: 'Watchdog' },
    { id: 'arch', icon: <BarChart3 />, label: 'Architecture' },
  ];

  const statusColor = systemStatus === 'RUNNING' ? 'status-green' :
                       systemStatus === 'PAUSED' ? 'status-yellow' : 'status-red';

  return (
    <div className="sidebar glass-panel" style={{ margin: '16px 0 16px 16px', height: 'calc(100vh - 32px)', borderRadius: '24px' }}>
      <div style={{ marginBottom: '32px' }}>
        <h1 className="text-gradient" style={{ fontSize: '28px', fontWeight: '700', letterSpacing: '-0.5px' }}>Jarvis</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '4px' }}>Command Center</p>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
        {navItems.map(item => (
          <div key={item.id} onClick={() => setActiveTab(item.id)} style={{
            display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', borderRadius: '12px', cursor: 'pointer',
            background: activeTab === item.id ? 'rgba(255,255,255,0.1)' : 'transparent',
            color: activeTab === item.id ? 'white' : 'var(--text-secondary)',
            transition: 'all 0.2s ease', fontWeight: activeTab === item.id ? '500' : '400',
          }}>
            {React.cloneElement(item.icon, { size: 18 })}
            <span style={{ fontSize: '14px' }}>{item.label}</span>
          </div>
        ))}
      </nav>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: 'auto' }}>
        <div className={`ws-badge ${wsConnected ? 'connected' : 'disconnected'}`}>
          {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
          <span>{wsConnected ? 'Live' : 'Disconnected'}</span>
        </div>
        <div className="glass-card" style={{ padding: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div className={`status-indicator ${statusColor}`}></div>
            <div>
              <h4 style={{ fontSize: '13px', fontWeight: '600' }}>System {systemStatus || '...'}</h4>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TOPBAR
// ═══════════════════════════════════════════════════════════════════
function Topbar({ portfolio, systemStatus, agentCount, onEvolution, onAudit, onPause, onResume }) {
  const isPaused = systemStatus === 'PAUSED';
  return (
    <div className="topbar glass-panel" style={{ margin: '16px 16px 0 16px', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flexWrap: 'wrap' }}>
        <div className="pill">
          <span className="pill-label">Equity:</span>
          <span className="pill-value">{fmtUSD(portfolio?.total_equity)}</span>
        </div>
        <div className="pill">
          <span className="pill-label">Daily P&L:</span>
          <span className="pill-value" style={{ color: portfolio?.daily_pnl >= 0 ? 'var(--pnl-positive)' : 'var(--pnl-negative)' }}>{fmtUSD(portfolio?.daily_pnl)}</span>
        </div>
        <div className="pill">
          <span className="pill-label">Agents:</span>
          <span className="pill-value">{agentCount ?? '-'}</span>
        </div>
        <div className="pill">
          <span className="pill-label">API Cost:</span>
          <span className="pill-value">{fmtUSD(portfolio?.total_api_cost_today)}</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {isPaused ? (
          <button className="btn btn-success" onClick={onResume}><Play size={16} /> Resume</button>
        ) : (
          <button className="btn btn-danger" onClick={onPause}><Pause size={16} /> Pause</button>
        )}
        <button className="btn btn-outline" onClick={onAudit}><Shield size={16} /> Audit</button>
        <button className="btn" onClick={onEvolution}><Zap size={16} /> Evolve</button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// OVERVIEW TAB
// ═══════════════════════════════════════════════════════════════════
function OverviewTab({ portfolio, bugSummary, velocity, costs, agentCount }) {
  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <h2 style={{ fontSize: '22px', fontWeight: '600', marginBottom: '20px' }}>System Overview</h2>
      
      {/* Financial Row */}
      <div className="finance-grid">
        <div className="glass-card">
          <p className="metric-label">Total Equity</p>
          <p className="metric-value">{fmtUSD(portfolio?.total_equity)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Daily P&L</p>
          <p className={`metric-value ${pnlClass(portfolio?.daily_pnl)}`}>{fmtUSD(portfolio?.daily_pnl)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Total P&L</p>
          <p className={`metric-value ${pnlClass(portfolio?.total_pnl)}`}>{fmtUSD(portfolio?.total_pnl)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Cash Available</p>
          <p className="metric-value">{fmtUSD(portfolio?.settled_cash)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">API Cost Today</p>
          <p className="metric-value negative">{fmtUSD(portfolio?.total_api_cost_today)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">API Cost All-Time</p>
          <p className="metric-value negative">{fmtUSD(portfolio?.total_api_cost_alltime)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Net P&L (After Costs)</p>
          <p className={`metric-value ${pnlClass(portfolio?.net_pnl)}`}>{fmtUSD(portfolio?.net_pnl)}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Drawdown</p>
          <p className={`metric-value ${portfolio?.drawdown_pct > 0 ? 'negative' : ''}`}>{fmt(portfolio?.drawdown_pct)}%</p>
        </div>
      </div>

      {/* Operational Row */}
      <h3 style={{ fontSize: '16px', fontWeight: '500', margin: '24px 0 12px 16px', color: 'var(--text-secondary)' }}>Operations</h3>
      <div className="finance-grid">
        <div className="glass-card">
          <p className="metric-label">Active Agents</p>
          <p className="metric-value">{agentCount ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Open Bugs</p>
          <p className={`metric-value ${bugSummary?.open > 0 ? 'negative' : ''}`}>{bugSummary?.open ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Bugs Resolved</p>
          <p className="metric-value positive">{bugSummary?.resolved ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Critical Bugs</p>
          <p className={`metric-value ${bugSummary?.critical > 0 ? 'negative' : ''}`}>{bugSummary?.critical ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">System Readiness</p>
          <p className="metric-value">{velocity?.readiness != null ? `${(velocity.readiness * 100).toFixed(0)}%` : '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Evolution Events</p>
          <p className="metric-value">{velocity?.evolution_events ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Total Files</p>
          <p className="metric-value">{velocity?.files_per_day ?? '-'}</p>
        </div>
        <div className="glass-card">
          <p className="metric-label">Total Lines</p>
          <p className="metric-value">{velocity?.lines_per_day?.toLocaleString() ?? '-'}</p>
        </div>
      </div>

      {/* Positions */}
      {portfolio?.positions && Object.keys(portfolio.positions).length > 0 && (
        <>
          <h3 style={{ fontSize: '16px', fontWeight: '500', margin: '24px 0 12px 16px', color: 'var(--text-secondary)' }}>Open Positions</h3>
          <div className="finance-grid">
            {Object.values(portfolio.positions).map((pos, i) => (
              <div key={i} className="glass-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontWeight: '600', fontSize: '16px' }}>{pos.ticker}</span>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{pos.side}</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '13px' }}>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Qty: </span>{fmt(pos.quantity, 4)}</div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Entry: </span>{fmtUSD(pos.avg_entry_price)}</div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Current: </span>{fmtUSD(pos.current_price)}</div>
                  <div><span style={{ color: pos.unrealized_pnl >= 0 ? 'var(--pnl-positive)' : 'var(--pnl-negative)' }}>P&L: {fmtUSD(pos.unrealized_pnl)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// AGENT DETAIL MODAL (fetches from /api/agents/{id})
// ═══════════════════════════════════════════════════════════════════
function AgentDetailModal({ agentId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!agentId) return;
    setLoading(true);
    fetchAgentDetail(agentId)
      .then(d => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [agentId]);

  if (!agentId) return null;

  const getBadgeClass = (type) => `badge-${type}`;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }} onClick={onClose}>
      <div className="glass-panel" onClick={e => e.stopPropagation()} style={{
        width: '640px', maxHeight: '85vh', overflowY: 'auto', padding: '28px', borderRadius: '24px',
      }}>
        {loading ? (
          <div className="loading-container" style={{ minHeight: '200px' }}><div className="spinner"></div><p>Loading agent details...</p></div>
        ) : !detail ? (
          <p style={{ color: 'var(--text-secondary)' }}>Failed to load agent details.</p>
        ) : (
          <>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
                  <h2 style={{ fontSize: '22px', fontWeight: '700' }}>{detail.name}</h2>
                  <span className={`agent-badge ${getBadgeClass(detail.type)}`}>{detail.type}</span>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>Role: <span style={{ color: 'var(--text-primary)' }}>{detail.role}</span> · Model: <span style={{ color: 'var(--accent-cyan)' }}>{detail.model || '-'}</span></p>
              </div>
              <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px' }}><X size={22} color="var(--text-secondary)" /></button>
            </div>

            {/* Metrics Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '24px' }}>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Trust</p>
                <p style={{ fontSize: '20px', fontWeight: '700' }}>{detail.metrics?.trust_weight != null ? `${(detail.metrics.trust_weight * 100).toFixed(0)}%` : '-'}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Brier Score</p>
                <p style={{ fontSize: '20px', fontWeight: '700' }}>{detail.metrics?.brier_score != null ? detail.metrics.brier_score.toFixed(3) : '—'}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Status</p>
                <p style={{ fontSize: '20px', fontWeight: '700', color: detail.status === 'ACTIVE' ? 'var(--status-green)' : 'var(--status-yellow)' }}>{detail.status}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Tasks Today</p>
                <p style={{ fontSize: '20px', fontWeight: '700' }}>{detail.metrics?.tasks_today ?? 0}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Tasks All-Time</p>
                <p style={{ fontSize: '20px', fontWeight: '700' }}>{detail.metrics?.tasks_alltime ?? 0}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Tokens Today</p>
                <p style={{ fontSize: '20px', fontWeight: '700' }}>{(detail.metrics?.tokens_today ?? 0).toLocaleString()}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Cost Today</p>
                <p className="metric-value negative" style={{ fontSize: '20px' }}>{fmtUSD(detail.metrics?.cost_today ?? 0)}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Cost All-Time</p>
                <p className="metric-value negative" style={{ fontSize: '20px' }}>{fmtUSD(detail.metrics?.cost_alltime ?? 0)}</p>
              </div>
              <div className="glass-card" style={{ padding: '12px' }}>
                <p className="metric-label">Failures</p>
                <p style={{ fontSize: '20px', fontWeight: '700', color: (detail.metrics?.consecutive_failures ?? 0) > 0 ? 'var(--status-red)' : 'var(--status-green)' }}>{detail.metrics?.consecutive_failures ?? 0}</p>
              </div>
            </div>

            {/* Skills */}
            {detail.skills && detail.skills.length > 0 && (
              <div style={{ marginBottom: '24px' }}>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '10px', color: 'var(--text-secondary)' }}>Skills</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {detail.skills.map((skill, i) => (
                    <span key={i} style={{
                      background: 'rgba(59, 130, 246, 0.15)', border: '1px solid rgba(59, 130, 246, 0.3)',
                      padding: '4px 12px', borderRadius: '20px', fontSize: '12px', color: 'var(--accent-blue)',
                    }}>{skill}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Goals */}
            {detail.goals && (
              <div>
                <h3 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '10px', color: 'var(--text-secondary)' }}>Goals</h3>
                <div className="glass-card" style={{
                  fontFamily: "'JetBrains Mono', 'Courier New', monospace", fontSize: '12px', lineHeight: '1.7',
                  whiteSpace: 'pre-wrap', maxHeight: '250px', overflowY: 'auto', color: 'var(--text-secondary)',
                }}>
                  {detail.goals}
                </div>
              </div>
            )}

            {/* Last Activity */}
            {detail.metrics?.last_activity && (
              <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '16px', textAlign: 'right' }}>
                Last active: {formatDatePST(detail.metrics.last_activity)}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// AGENT REGISTRY TAB (Real Data)
// ═══════════════════════════════════════════════════════════════════
function AgentRegistryTab({ agents, onAudit }) {
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const getBadgeClass = (type) => `badge-${type}`;

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: '600' }}>Agent Ecosystem</h2>
        <button className="btn btn-outline" onClick={onAudit}><Search size={16} /> Run Audit</button>
      </div>
      <div className="agent-grid">
        {agents.map((agent, i) => (
          <div key={agent.id || i} className="glass-card" onClick={() => setSelectedAgentId(agent.id)} style={{ display: 'flex', flexDirection: 'column', gap: '14px', cursor: 'pointer' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: '600', fontSize: '15px' }}>{agent.name}</span>
              <span className={`agent-badge ${getBadgeClass(agent.type)}`}>{agent.type}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Trust</p>
                <p style={{ fontSize: '15px', fontWeight: '600' }}>{agent.trust_weight != null ? `${(agent.trust_weight * 100).toFixed(0)}%` : '-'}</p>
              </div>
              <div>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Brier</p>
                <p style={{ fontSize: '15px', fontWeight: '600' }}>{agent.brier_score != null ? agent.brier_score.toFixed(2) : '—'}</p>
              </div>
              <div>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Tasks</p>
                <p style={{ fontSize: '15px', fontWeight: '600' }}>{agent.tasks_today ?? 0}</p>
              </div>
              <div>
                <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '2px' }}>Cost</p>
                <p style={{ fontSize: '15px', fontWeight: '600' }}>{fmtUSD(agent.cost_today ?? 0)}</p>
              </div>
            </div>
            <div style={{ height: '3px', background: 'rgba(255,255,255,0.08)', width: '100%', borderRadius: '2px', marginTop: 'auto' }}>
              <div style={{
                height: '100%', borderRadius: '2px',
                width: `${Math.min(100, (agent.trust_weight ?? 1) * 100)}%`,
                background: agent.status === 'ACTIVE' ? 'var(--status-green)' : 'var(--status-yellow)',
              }}></div>
            </div>
          </div>
        ))}
      </div>
      {selectedAgentId && <AgentDetailModal agentId={selectedAgentId} onClose={() => setSelectedAgentId(null)} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// PORTFOLIO TAB
// ═══════════════════════════════════════════════════════════════════
function PortfolioTab({ portfolio, costs, trades }) {
  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <h2 style={{ fontSize: '22px', fontWeight: '600', marginBottom: '20px' }}>Portfolio & Financial Details</h2>

      {/* Cost Breakdown by Agent */}
      {costs?.breakdown_by_agent && (
        <>
          <h3 style={{ fontSize: '16px', fontWeight: '500', margin: '0 0 12px 0', color: 'var(--text-secondary)' }}>Cost by Agent</h3>
          <div className="finance-grid" style={{ marginBottom: '24px' }}>
            {Object.entries(costs.breakdown_by_agent).filter(([, v]) => v > 0).map(([name, cost]) => (
              <div key={name} className="glass-card">
                <p className="metric-label">{name}</p>
                <p className="metric-value negative">{fmtUSD(cost)}</p>
              </div>
            ))}
            {Object.values(costs.breakdown_by_agent).every(v => v === 0) && (
              <div className="glass-card"><p className="metric-label">No API costs recorded yet</p><p className="metric-value">$0.00</p></div>
            )}
          </div>
        </>
      )}

      {/* Recent Trades */}
      <h3 style={{ fontSize: '16px', fontWeight: '500', margin: '0 0 12px 0', color: 'var(--text-secondary)' }}>Recent Trades</h3>
      {trades?.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {trades.slice(0, 20).map((t, i) => (
            <div key={t.id || i} className="glass-card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px' }}>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <span style={{ fontWeight: '600' }}>{t.ticker}</span>
                <span style={{ fontSize: '12px', color: t.side === 'BUY' ? 'var(--pnl-positive)' : 'var(--pnl-negative)' }}>{t.side}</span>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{t.division}</span>
              </div>
              <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
                <span>{fmtUSD(t.notional)}</span>
                {t.realized_pnl != null && <span style={{ color: t.realized_pnl >= 0 ? 'var(--pnl-positive)' : 'var(--pnl-negative)' }}>P&L: {fmtUSD(t.realized_pnl)}</span>}
                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{t.status}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="glass-card"><p style={{ color: 'var(--text-secondary)' }}>No trades recorded yet.</p></div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// BUG DETAIL MODAL
// ═══════════════════════════════════════════════════════════════════
function BugDetailModal({ bug, onClose }) {
  if (!bug) return null;

  const severityColors = {
    CRITICAL: { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.4)', text: '#F87171' },
    HIGH:     { bg: 'rgba(249, 115, 22, 0.15)', border: 'rgba(249, 115, 22, 0.4)', text: '#FB923C' },
    MEDIUM:   { bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.4)', text: '#FBBF24' },
    LOW:      { bg: 'rgba(59, 130, 246, 0.15)', border: 'rgba(59, 130, 246, 0.4)', text: '#60A5FA' },
  };

  const statusConfig = {
    OPEN:        { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.4)', text: '#F87171', icon: '🔴' },
    IN_PROGRESS: { bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.4)', text: '#FBBF24', icon: '🟡' },
    RESOLVED:    { bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.4)', text: '#34D399', icon: '✅' },
    WONT_FIX:    { bg: 'rgba(107, 114, 128, 0.15)', border: 'rgba(107, 114, 128, 0.4)', text: '#9CA3AF', icon: '⏭️' },
    DEFERRED:    { bg: 'rgba(139, 92, 246, 0.15)', border: 'rgba(139, 92, 246, 0.4)', text: '#A78BFA', icon: '⏸️' },
  };

  const sev = severityColors[bug.severity] || severityColors.MEDIUM;
  const stat = statusConfig[bug.status] || statusConfig.OPEN;



  const timeAgo = (iso) => {
    if (!iso) return '';
    try {
      const now = new Date();
      const then = new Date(iso);
      const diffMs = now - then;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHrs = Math.floor(diffMins / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      const diffDays = Math.floor(diffHrs / 24);
      return `${diffDays}d ago`;
    } catch { return ''; }
  };

  // Duration from created to resolved
  const duration = () => {
    if (!bug.created_at || !bug.resolved_at) return null;
    try {
      const created = new Date(bug.created_at);
      const resolved = new Date(bug.resolved_at);
      const diffMs = resolved - created;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 60) return `${diffMins} minutes`;
      const diffHrs = Math.floor(diffMins / 60);
      if (diffHrs < 24) return `${diffHrs} hours`;
      const diffDays = Math.floor(diffHrs / 24);
      return `${diffDays} days`;
    } catch { return null; }
  };

  const isAutoFiled = bug.title?.startsWith('[Auto]') || bug.source === 'bug_scanner' || bug.source === 'process_monitor';

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 200,
    }} onClick={onClose}>
      <div className="glass-panel" onClick={e => e.stopPropagation()} style={{
        width: '720px', maxHeight: '85vh', overflowY: 'auto', padding: '32px', borderRadius: '24px',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
          <div style={{ flex: 1, marginRight: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px', flexWrap: 'wrap' }}>
              <span style={{
                background: sev.bg, border: `1px solid ${sev.border}`, color: sev.text,
                padding: '3px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', letterSpacing: '0.5px',
              }}>{bug.severity}</span>
              <span style={{
                background: stat.bg, border: `1px solid ${stat.border}`, color: stat.text,
                padding: '3px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '700', letterSpacing: '0.5px',
              }}>{stat.icon} {bug.status}</span>
              {isAutoFiled && (
                <span style={{
                  background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.3)',
                  padding: '3px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: '600', color: '#A78BFA',
                }}>🤖 Auto-filed</span>
              )}
            </div>
            <h2 style={{ fontSize: '20px', fontWeight: '700', lineHeight: '1.4' }}>{bug.title}</h2>
            {bug.created_at && (
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px' }}>
                Filed {formatDatePST(bug.created_at)} <span style={{ color: 'var(--text-muted)' }}>({timeAgo(bug.created_at)})</span>
              </p>
            )}
          </div>
          <button onClick={onClose} style={{
            background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '10px', cursor: 'pointer', padding: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s ease',
          }}>
            <X size={18} color="var(--text-secondary)" />
          </button>
        </div>

        {/* Timeline */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px', marginBottom: '24px',
        }}>
          <div className="glass-card" style={{ padding: '14px' }}>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Created</p>
            <p style={{ fontSize: '14px', fontWeight: '600' }}>{formatDatePST(bug.created_at) || '—'}</p>
          </div>
          {bug.started_at && (
            <div className="glass-card" style={{ padding: '14px' }}>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Work Started</p>
              <p style={{ fontSize: '14px', fontWeight: '600' }}>{formatDatePST(bug.started_at)}</p>
            </div>
          )}
          {bug.resolved_at && (
            <div className="glass-card" style={{ padding: '14px' }}>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Resolved</p>
              <p style={{ fontSize: '14px', fontWeight: '600', color: 'var(--status-green)' }}>{formatDatePST(bug.resolved_at)}</p>
            </div>
          )}
          {duration() && (
            <div className="glass-card" style={{ padding: '14px' }}>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Resolution Time</p>
              <p style={{ fontSize: '14px', fontWeight: '600', color: 'var(--accent-cyan)' }}>{duration()}</p>
            </div>
          )}
        </div>

        {/* Description */}
        {bug.description && (
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Description</h3>
            <div className="glass-card" style={{
              fontFamily: "'JetBrains Mono', 'Courier New', monospace", fontSize: '12px', lineHeight: '1.8',
              whiteSpace: 'pre-wrap', maxHeight: '300px', overflowY: 'auto', color: 'var(--text-secondary)', padding: '18px',
            }}>
              {bug.description}
            </div>
          </div>
        )}

        {/* Metadata Grid */}
        <div style={{ marginBottom: '24px' }}>
          <h3 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Details</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div className="glass-card" style={{ padding: '14px' }}>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Source</p>
              <p style={{ fontSize: '14px', fontWeight: '500' }}>{bug.source || 'Manual'}</p>
            </div>
            <div className="glass-card" style={{ padding: '14px' }}>
              <p style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>Assigned To</p>
              <p style={{ fontSize: '14px', fontWeight: '500' }}>{bug.assigned_to || 'Unassigned'}</p>
            </div>
          </div>
        </div>

        {/* PR Link */}
        {bug.pr_url && (
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '10px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Pull Request</h3>
            <a href={bug.pr_url} target="_blank" rel="noopener noreferrer" className="glass-card" style={{
              display: 'flex', alignItems: 'center', gap: '10px', textDecoration: 'none', color: 'var(--accent-blue)', padding: '14px',
            }}>
              <GitPullRequest size={16} />
              <span style={{ fontSize: '13px', fontWeight: '500' }}>{bug.pr_url}</span>
            </a>
          </div>
        )}

        {/* Worker Error */}
        {bug.worker_error && (
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{ fontSize: '13px', fontWeight: '600', marginBottom: '10px', color: 'var(--status-red)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Worker Error</h3>
            <div className="glass-card" style={{
              fontFamily: "'JetBrains Mono', 'Courier New', monospace", fontSize: '12px', lineHeight: '1.6',
              whiteSpace: 'pre-wrap', color: 'var(--status-red)', padding: '18px',
              background: 'rgba(239, 68, 68, 0.05)', borderColor: 'rgba(239, 68, 68, 0.2)',
            }}>
              {bug.worker_error}
            </div>
          </div>
        )}

        {/* Bug ID */}
        <p style={{ fontSize: '11px', color: 'var(--text-muted)', textAlign: 'right', fontFamily: 'monospace' }}>
          ID: {bug.id}
        </p>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// BUG PIPELINE TAB
// ═══════════════════════════════════════════════════════════════════
function BugTab({ bugSummary, bugs }) {
  const [selectedBug, setSelectedBug] = useState(null);
  const [filter, setFilter] = useState('ALL');

  const severityColors = {
    CRITICAL: '#F87171',
    HIGH: '#FB923C',
    MEDIUM: '#FBBF24',
    LOW: '#60A5FA',
  };

  const statusBadge = (status) => {
    const cfg = {
      OPEN:        { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.3)', text: '#F87171' },
      IN_PROGRESS: { bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.3)', text: '#FBBF24' },
      RESOLVED:    { bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.3)', text: '#34D399' },
      WONT_FIX:    { bg: 'rgba(107, 114, 128, 0.15)', border: 'rgba(107, 114, 128, 0.3)', text: '#9CA3AF' },
      DEFERRED:    { bg: 'rgba(139, 92, 246, 0.15)', border: 'rgba(139, 92, 246, 0.3)', text: '#A78BFA' },
    };
    const c = cfg[status] || cfg.OPEN;
    return c;
  };

  const filteredBugs = (bugs || []).filter(b => {
    if (filter === 'ALL') return true;
    return b.status === filter;
  });

  const timeAgo = (iso) => {
    if (!iso) return '';
    try {
      const now = new Date();
      const then = new Date(iso);
      const diffMs = now - then;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins < 60) return `${diffMins}m ago`;
      const diffHrs = Math.floor(diffMins / 60);
      if (diffHrs < 24) return `${diffHrs}h ago`;
      const diffDays = Math.floor(diffHrs / 24);
      return `${diffDays}d ago`;
    } catch { return ''; }
  };

  const filters = [
    { key: 'ALL', label: 'All', count: bugs?.length || 0 },
    { key: 'OPEN', label: 'Open', count: bugSummary?.open || 0 },
    { key: 'IN_PROGRESS', label: 'In Progress', count: bugSummary?.in_progress || 0 },
    { key: 'RESOLVED', label: 'Resolved', count: bugSummary?.resolved || 0 },
  ];

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ fontSize: '22px', fontWeight: '600' }}>Bug Pipeline</h2>
      </div>

      {/* Summary Cards */}
      <div className="finance-grid" style={{ marginBottom: '8px' }}>
        <div className="glass-card"><p className="metric-label">Total Bugs</p><p className="metric-value">{bugSummary?.total ?? '-'}</p></div>
        <div className="glass-card"><p className="metric-label">Open</p><p className={`metric-value ${bugSummary?.open > 0 ? 'negative' : ''}`}>{bugSummary?.open ?? '-'}</p></div>
        <div className="glass-card"><p className="metric-label">In Progress</p><p className="metric-value" style={{ color: 'var(--status-yellow)' }}>{bugSummary?.in_progress ?? '-'}</p></div>
        <div className="glass-card"><p className="metric-label">Resolved</p><p className="metric-value positive">{bugSummary?.resolved ?? '-'}</p></div>
        <div className="glass-card"><p className="metric-label">Critical</p><p className={`metric-value ${bugSummary?.critical > 0 ? 'negative' : ''}`}>{bugSummary?.critical ?? '-'}</p></div>
        <div className="glass-card"><p className="metric-label">High Severity</p><p className={`metric-value ${bugSummary?.high > 0 ? 'negative' : ''}`}>{bugSummary?.high ?? '-'}</p></div>
      </div>

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', padding: '0 16px' }}>
        {filters.map(f => (
          <button key={f.key} onClick={() => setFilter(f.key)} style={{
            background: filter === f.key ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.03)',
            border: `1px solid ${filter === f.key ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.06)'}`,
            borderRadius: '8px', padding: '6px 14px', color: filter === f.key ? 'white' : 'var(--text-secondary)',
            fontSize: '13px', fontWeight: filter === f.key ? '600' : '400',
            cursor: 'pointer', transition: 'all 0.2s ease', fontFamily: 'var(--font-main)',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}>
            {f.label}
            <span style={{
              background: filter === f.key ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.06)',
              padding: '1px 7px', borderRadius: '10px', fontSize: '11px', fontWeight: '600',
            }}>{f.count}</span>
          </button>
        ))}
      </div>

      {/* Bug List */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', padding: '0 16px' }}>
        {filteredBugs.length === 0 ? (
          <div className="glass-card" style={{ textAlign: 'center', padding: '40px 20px' }}>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
              {filter === 'ALL' ? 'No bugs in the tracker.' : `No ${filter.toLowerCase().replace('_', ' ')} bugs.`}
            </p>
          </div>
        ) : (
          filteredBugs.map((bug) => {
            const sevColor = severityColors[bug.severity] || severityColors.MEDIUM;
            const sc = statusBadge(bug.status);
            return (
              <div
                key={bug.id}
                onClick={() => setSelectedBug(bug)}
                className="bug-row"
                style={{
                  display: 'flex', alignItems: 'center', gap: '14px',
                  padding: '14px 18px', borderRadius: '12px', cursor: 'pointer',
                  background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)',
                  transition: 'all 0.2s ease',
                }}
              >
                {/* Severity dot */}
                <div style={{
                  width: '10px', height: '10px', borderRadius: '50%', flexShrink: 0,
                  background: sevColor, boxShadow: `0 0 8px ${sevColor}`,
                }} />

                {/* Title + metadata */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{
                    fontSize: '14px', fontWeight: '500', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>{bug.title}</p>
                  <div style={{ display: 'flex', gap: '12px', marginTop: '4px', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{timeAgo(bug.created_at)}</span>
                    {bug.source && (
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>via {bug.source}</span>
                    )}
                    <span style={{ fontSize: '11px', color: sevColor, fontWeight: '600' }}>{bug.severity}</span>
                  </div>
                </div>

                {/* Status badge */}
                <span style={{
                  background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text,
                  padding: '4px 12px', borderRadius: '6px', fontSize: '11px', fontWeight: '700',
                  letterSpacing: '0.3px', flexShrink: 0,
                }}>{bug.status}</span>
              </div>
            );
          })
        )}
      </div>

      {/* Detail Modal */}
      {selectedBug && <BugDetailModal bug={selectedBug} onClose={() => setSelectedBug(null)} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// WATCHDOG TAB
// ═══════════════════════════════════════════════════════════════════
function WatchdogTab({ watchdogLogs }) {
  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <h2 style={{ fontSize: '22px', fontWeight: '600', marginBottom: '20px' }}>Watchdog Logs</h2>
      <div className="glass-card" style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '12px', lineHeight: '1.8', whiteSpace: 'pre-wrap', maxHeight: '600px', overflowY: 'auto' }}>
        {watchdogLogs?.length > 0 ? watchdogLogs.map((line, i) => (
          <div key={i} style={{ color: line.includes('❌') || line.includes('ERROR') ? 'var(--status-red)' : line.includes('✅') ? 'var(--status-green)' : line.includes('⚠️') ? 'var(--status-yellow)' : 'var(--text-secondary)' }}>
            {line}
          </div>
        )) : <p style={{ color: 'var(--text-secondary)' }}>No watchdog logs available. Run the watchdog service to generate reports.</p>}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// ARCHITECTURE TAB (ReactFlow) — 5-Division Hierarchy
// ═══════════════════════════════════════════════════════════════════

// Division color scheme
const DIVISION_COLORS = {
  ceo:       { border: '#3B82F6', bg: 'rgba(59, 130, 246, 0.12)', label: '#93C5FD' },
  csuite:    { border: '#A78BFA', bg: 'rgba(167, 139, 250, 0.12)', label: '#C4B5FD' },
  research:  { border: '#34D399', bg: 'rgba(52, 211, 153, 0.10)', label: '#6EE7B7' },
  trading:   { border: '#F59E0B', bg: 'rgba(245, 158, 11, 0.10)', label: '#FCD34D' },
  evolution: { border: '#EC4899', bg: 'rgba(236, 72, 153, 0.10)', label: '#F9A8D4' },
  ops:       { border: '#06B6D4', bg: 'rgba(6, 182, 212, 0.10)', label: '#67E8F9' },
};

// Map agent role → division
const ROLE_DIVISION = {
  MASTER: 'ceo',
  CTO: 'csuite', CSO: 'csuite', CRO: 'csuite',
  PRODUCT: 'research', FUNDAMENTAL_ANALYST: 'research', TECHNICAL_ANALYST: 'research',
  SENTIMENT_ANALYST: 'research', MACRO_ANALYST: 'research', STRATEGY_RESEARCHER: 'research',
  PORTFOLIO_MANAGER: 'trading', BULL: 'trading', BEAR: 'trading', JUDGE: 'trading',
  META_REVIEW: 'evolution', DEVELOPER: 'evolution', PERFORMANCE_ANALYST: 'evolution',
  QA: 'ops', AUDITOR: 'ops', JOURNALING: 'ops', WATCHDOG: 'ops',
};

// Map agent role → parent role for hierarchy edges
const REPORTING_HIERARCHY = {
  // C-Suite → Jarvis
  CTO: 'MASTER', CSO: 'MASTER', CRO: 'MASTER',
  // Division Directors → Jarvis
  PRODUCT: 'MASTER', PORTFOLIO_MANAGER: 'MASTER', META_REVIEW: 'MASTER', QA: 'MASTER',
  // Research Division → Product Agent
  FUNDAMENTAL_ANALYST: 'PRODUCT', TECHNICAL_ANALYST: 'PRODUCT',
  SENTIMENT_ANALYST: 'PRODUCT', MACRO_ANALYST: 'PRODUCT', STRATEGY_RESEARCHER: 'PRODUCT',
  // Trading Division → Portfolio Manager
  BULL: 'PORTFOLIO_MANAGER', BEAR: 'PORTFOLIO_MANAGER', JUDGE: 'PORTFOLIO_MANAGER',
  // Evolution Division → Meta-Review Agent
  DEVELOPER: 'META_REVIEW', PERFORMANCE_ANALYST: 'META_REVIEW',
  // Operations Division → QA Agent
  AUDITOR: 'QA', JOURNALING: 'QA', WATCHDOG: 'QA',
};

function ArchitectureTab({ agents }) {
  const [selectedAgentId, setSelectedAgentId] = useState(null);

  // Build agent lookup by role
  const agentByRole = {};
  agents.forEach(a => { agentByRole[a.role] = a; });

  // Determine which agents exist — include placeholders for expected agents
  const ALL_EXPECTED_ROLES = [
    'MASTER',
    'CTO', 'CSO', 'CRO',
    'PRODUCT', 'FUNDAMENTAL_ANALYST', 'TECHNICAL_ANALYST', 'SENTIMENT_ANALYST', 'MACRO_ANALYST', 'STRATEGY_RESEARCHER',
    'PORTFOLIO_MANAGER', 'BULL', 'BEAR', 'JUDGE',
    'META_REVIEW', 'DEVELOPER', 'PERFORMANCE_ANALYST',
    'QA', 'AUDITOR', 'JOURNALING', 'WATCHDOG',
  ];

  const ROLE_LABELS = {
    MASTER: 'Jarvis (CEO)', CTO: 'CTO Agent', CSO: 'CSO Agent', CRO: 'CRO Agent',
    PRODUCT: 'Product Agent\n(Research Dir.)', FUNDAMENTAL_ANALYST: 'Fundamental\nAnalyst',
    TECHNICAL_ANALYST: 'Technical\nAnalyst', SENTIMENT_ANALYST: 'Sentiment\nAnalyst',
    MACRO_ANALYST: 'Macro\nAnalyst', STRATEGY_RESEARCHER: 'Strategy\nResearcher',
    PORTFOLIO_MANAGER: 'Portfolio Mgr\n(Trading Dir.)', BULL: 'Bull Agent', BEAR: 'Bear Agent', JUDGE: 'Judge Agent',
    META_REVIEW: 'Meta-Review\n(Evo. Dir.)', DEVELOPER: 'Developer\nAgent', PERFORMANCE_ANALYST: 'Performance\nAnalyst',
    QA: 'QA Agent\n(Ops Dir.)', AUDITOR: 'Auditor\nAgent', JOURNALING: 'Journaling\nAgent', WATCHDOG: 'Watchdog\nAgent',
  };

  // Layout positions — structured as a tree with division grouping
  const POSITIONS = {
    // CEO at top center
    MASTER:             { x: 480, y: 20 },
    // C-Suite (row 1)
    CTO:                { x: 120, y: 140 },
    CSO:                { x: 320, y: 140 },
    CRO:                { x: 520, y: 140 },
    // Division Directors (row 2) — spread across
    PRODUCT:            { x: 80,  y: 280 },
    PORTFOLIO_MANAGER:  { x: 340, y: 280 },
    META_REVIEW:        { x: 600, y: 280 },
    QA:                 { x: 860, y: 280 },
    // Research Division (row 3, left cluster)
    FUNDAMENTAL_ANALYST:{ x: -80, y: 420 },
    TECHNICAL_ANALYST:  { x: 40,  y: 420 },
    SENTIMENT_ANALYST:  { x: 160, y: 420 },
    MACRO_ANALYST:      { x: 280, y: 420 },
    STRATEGY_RESEARCHER:{ x: 100, y: 530 },
    // Trading Division (row 3, center-left cluster)
    BULL:               { x: 280, y: 420 },
    BEAR:               { x: 400, y: 420 },
    JUDGE:              { x: 340, y: 530 },
    // Evolution Division (row 3, center-right cluster)
    DEVELOPER:          { x: 540, y: 420 },
    PERFORMANCE_ANALYST:{ x: 680, y: 420 },
    // Operations Division (row 3, right cluster)
    AUDITOR:            { x: 780, y: 420 },
    JOURNALING:         { x: 900, y: 420 },
    WATCHDOG:           { x: 840, y: 530 },
  };

  // Adjust positions to avoid overlap — spread out research/trading
  const adjustedPositions = { ...POSITIONS };
  adjustedPositions.FUNDAMENTAL_ANALYST = { x: -100, y: 430 };
  adjustedPositions.TECHNICAL_ANALYST =   { x: 20,   y: 430 };
  adjustedPositions.SENTIMENT_ANALYST =   { x: 140,  y: 430 };
  adjustedPositions.MACRO_ANALYST =       { x: 100,  y: 540 };
  adjustedPositions.STRATEGY_RESEARCHER = { x: -20,  y: 540 };
  adjustedPositions.BULL =                { x: 280,  y: 430 };
  adjustedPositions.BEAR =                { x: 400,  y: 430 };
  adjustedPositions.JUDGE =               { x: 340,  y: 540 };
  adjustedPositions.DEVELOPER =           { x: 540,  y: 430 };
  adjustedPositions.PERFORMANCE_ANALYST = { x: 670,  y: 430 };
  adjustedPositions.AUDITOR =             { x: 790,  y: 430 };
  adjustedPositions.JOURNALING =          { x: 910,  y: 430 };
  adjustedPositions.WATCHDOG =            { x: 850,  y: 540 };

  // Build nodes
  const nodeStyle = (role) => {
    const div = ROLE_DIVISION[role] || 'csuite';
    const colors = DIVISION_COLORS[div];
    const agent = agentByRole[role];
    const isActive = agent?.status === 'ACTIVE';
    const isMissing = !agent;

    return {
      background: isMissing ? 'rgba(255,255,255,0.02)' : colors.bg,
      color: 'white',
      border: `2px solid ${isMissing ? 'rgba(255,255,255,0.15)' : colors.border}`,
      borderRadius: role === 'MASTER' ? '16px' : '10px',
      padding: role === 'MASTER' ? '14px 22px' : '10px 14px',
      cursor: agent ? 'pointer' : 'default',
      fontSize: role === 'MASTER' ? '14px' : '11px',
      fontWeight: role === 'MASTER' ? '700' : '500',
      textAlign: 'center',
      opacity: isMissing ? 0.4 : 1,
      boxShadow: isActive ? `0 0 12px ${colors.border}40` : 'none',
      minWidth: role === 'MASTER' ? '120px' : '90px',
    };
  };

  const nodes = ALL_EXPECTED_ROLES.map(role => {
    const agent = agentByRole[role];
    const pos = adjustedPositions[role] || { x: 500, y: 400 };
    const label = agent?.name || ROLE_LABELS[role] || role;
    const statusDot = agent ? (agent.status === 'ACTIVE' ? '🟢 ' : agent.status === 'ERROR' ? '🔴 ' : '🟡 ') : '⚪ ';

    return {
      id: role,
      position: pos,
      data: { label: role === 'MASTER' ? `🤖 ${label}` : `${statusDot}${label}` },
      style: nodeStyle(role),
    };
  });

  // Build edges from reporting hierarchy
  const edges = Object.entries(REPORTING_HIERARCHY).map(([childRole, parentRole]) => {
    const div = ROLE_DIVISION[childRole] || 'csuite';
    const colors = DIVISION_COLORS[div];
    const childExists = !!agentByRole[childRole];
    const parentExists = !!agentByRole[parentRole];

    return {
      id: `e-${parentRole}-${childRole}`,
      source: parentRole,
      target: childRole,
      animated: childExists && parentExists,
      style: {
        stroke: colors.border,
        strokeWidth: childExists ? 2 : 1,
        opacity: (childExists && parentExists) ? 0.8 : 0.25,
      },
    };
  });

  const handleNodeClick = (_event, node) => {
    const agent = agentByRole[node.id];
    if (agent?.id) setSelectedAgentId(agent.id);
  };

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      {/* Legend */}
      <div style={{
        position: 'absolute', top: '16px', right: '16px', zIndex: 10,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
        borderRadius: '12px', padding: '14px 18px', border: '1px solid rgba(255,255,255,0.1)',
      }}>
        <p style={{ fontSize: '11px', fontWeight: '600', marginBottom: '8px', color: 'var(--text-secondary)', letterSpacing: '0.5px' }}>DIVISIONS</p>
        {[
          { key: 'csuite', label: 'C-Suite (Executive)' },
          { key: 'research', label: 'Research Division' },
          { key: 'trading', label: 'Trading Division' },
          { key: 'evolution', label: 'Evolution Division' },
          { key: 'ops', label: 'Operations Division' },
        ].map(d => (
          <div key={d.key} style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '3px', background: DIVISION_COLORS[d.key].border }} />
            <span style={{ fontSize: '11px', color: DIVISION_COLORS[d.key].label }}>{d.label}</span>
          </div>
        ))}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', marginTop: '8px', paddingTop: '8px' }}>
          <p style={{ fontSize: '10px', color: 'var(--text-muted)' }}>🟢 Active  🟡 Idle  🔴 Error  ⚪ Not deployed</p>
        </div>
      </div>

      {/* Title */}
      <div style={{
        position: 'absolute', top: '16px', left: '16px', zIndex: 10,
      }}>
        <h2 style={{ fontSize: '20px', fontWeight: '600', marginBottom: '4px' }}>Interactive System Architecture</h2>
        <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
          Click on any agent node to drill down into their details, tasks, and models used.
        </p>
      </div>

      {/* Agent count badge */}
      <div style={{
        position: 'absolute', top: '16px', right: '220px', zIndex: 10,
        background: 'rgba(52, 211, 153, 0.15)', border: '1px solid rgba(52, 211, 153, 0.3)',
        borderRadius: '20px', padding: '6px 14px', fontSize: '12px', fontWeight: '600', color: '#34D399',
      }}>
        {agents.length} active agents
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
      >
        <Background color="#fff" gap={16} size={1} opacity={0.03} />
        <Controls style={{ background: 'var(--bg-glass)', border: '1px solid rgba(255,255,255,0.1)', fill: 'white' }} />
      </ReactFlow>

      {selectedAgentId && <AgentDetailModal agentId={selectedAgentId} onClose={() => setSelectedAgentId(null)} />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// LIVE FEED
// ═══════════════════════════════════════════════════════════════════
function Feed({ logs }) {
  return (
    <div className="bottom-feed glass-panel" style={{ margin: '0 16px 16px 16px', borderRadius: '24px' }}>
      <h3 style={{ fontSize: '13px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
        <Activity size={14} color="var(--accent-cyan)" /> Live Activity Feed
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {logs.length === 0 && <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Waiting for events...</p>}
        {logs.map((log, idx) => (
          <div key={idx} style={{ display: 'flex', gap: '12px', fontSize: '12px', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace', minWidth: '75px' }}>{log.time}</span>
            {log.type === 'error' && <AlertTriangle size={12} color="var(--status-red)" />}
            {log.type === 'warning' && <AlertTriangle size={12} color="var(--status-yellow)" />}
            {log.type === 'info' && <span className="status-indicator status-green" style={{ width: '5px', height: '5px' }}></span>}
            <span style={{ color: log.type === 'error' ? 'var(--status-red)' : 'var(--text-primary)' }}>{log.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// APP (Main)
// ═══════════════════════════════════════════════════════════════════
export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);

  // Real data states
  const [systemStatus, setSystemStatus] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [agents, setAgents] = useState([]);
  const [bugSummary, setBugSummary] = useState(null);
  const [bugs, setBugs] = useState([]);
  const [costs, setCosts] = useState(null);
  const [velocity, setVelocity] = useState(null);
  const [watchdogLogs, setWatchdogLogs] = useState([]);
  const [trades, setTrades] = useState([]);
  const [feedLogs, setFeedLogs] = useState([]);

  const addLog = (msg, type = 'info') => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, timeZone: PST_TIMEZONE });
    setFeedLogs(prev => [{ time, msg, type }, ...prev].slice(0, 50));
  };

  // ── Initial data fetch ─────────────────────────────────────────
  useEffect(() => {
    async function loadAll() {
      try {
        setLoading(true);
        setError(null);

        const [statusData, agentsData, bugData, bugsListData, costData, velData, wdData, tradeData] = await Promise.allSettled([
          fetchSystemStatus(),
          fetchAgents(),
          fetchBugSummary(),
          fetchBugs(),
          fetchCosts(),
          fetchVelocity(),
          fetchWatchdog(),
          fetchTrades(),
        ]);

        if (statusData.status === 'fulfilled') {
          setSystemStatus(statusData.value.status);
          setPortfolio(statusData.value.portfolio);
        }
        if (agentsData.status === 'fulfilled') setAgents(agentsData.value.agents || []);
        if (bugData.status === 'fulfilled') setBugSummary(bugData.value);
        if (bugsListData.status === 'fulfilled') setBugs(bugsListData.value.bugs || []);
        if (costData.status === 'fulfilled') setCosts(costData.value);
        if (velData.status === 'fulfilled') setVelocity(velData.value);
        if (wdData.status === 'fulfilled') setWatchdogLogs(wdData.value.logs || []);
        if (tradeData.status === 'fulfilled') setTrades(tradeData.value.trades || []);

        addLog('Dashboard connected to Jarvis backend', 'info');
        setLoading(false);
      } catch (e) {
        setError(e.message);
        addLog(`Failed to connect: ${e.message}`, 'error');
        setLoading(false);
      }
    }
    loadAll();
  }, []);

  // ── WebSocket for live updates ─────────────────────────────────
  useEffect(() => {
    const ws = connectWebSocket((data) => {
      setWsConnected(true);
      if (data.type === 'status_update' && data.data) {
        setSystemStatus(data.data.status);
        if (data.data.portfolio) setPortfolio(data.data.portfolio);
      }
      if (data.type === 'evolution_forced') addLog('Evolution cycle triggered', 'warning');
      if (data.type === 'system_paused') { setSystemStatus('PAUSED'); addLog('System PAUSED', 'warning'); }
      if (data.type === 'system_resumed') { setSystemStatus('RUNNING'); addLog('System RESUMED', 'info'); }
      if (data.type === 'audit_complete') addLog(`Audit complete — readiness: ${data.readiness}`, 'info');
    });
    return () => ws?.close();
  }, []);

  // ── Periodic refresh (every 30s) ──────────────────────────────
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const [agentsData, bugData, bugsListData] = await Promise.allSettled([fetchAgents(), fetchBugSummary(), fetchBugs()]);
        if (agentsData.status === 'fulfilled') setAgents(agentsData.value.agents || []);
        if (bugData.status === 'fulfilled') setBugSummary(bugData.value);
        if (bugsListData.status === 'fulfilled') setBugs(bugsListData.value.bugs || []);
      } catch (e) { /* silent */ }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // ── Control handlers ──────────────────────────────────────────
  const handleEvolution = async () => {
    try { await forceEvolution(); addLog('Evolution cycle triggered by owner', 'warning'); } catch (e) { addLog(`Evolution failed: ${e.message}`, 'error'); }
  };
  const handleAudit = async () => {
    try { const r = await forceAudit(); addLog(`Audit complete — readiness: ${r.readiness ?? 'N/A'}`, 'info'); } catch (e) { addLog(`Audit failed: ${e.message}`, 'error'); }
  };
  const handlePause = async () => {
    try { await pauseSystem(); setSystemStatus('PAUSED'); addLog('System paused by owner', 'warning'); } catch (e) { addLog(`Pause failed: ${e.message}`, 'error'); }
  };
  const handleResume = async () => {
    try { await resumeSystem(); setSystemStatus('RUNNING'); addLog('System resumed by owner', 'info'); } catch (e) { addLog(`Resume failed: ${e.message}`, 'error'); }
  };

  // ── Render ────────────────────────────────────────────────────
  const renderContent = () => {
    if (loading) return <div className="loading-container"><div className="spinner"></div><p>Connecting to Jarvis backend...</p></div>;
    
    switch (activeTab) {
      case 'overview': return <OverviewTab portfolio={portfolio} bugSummary={bugSummary} velocity={velocity} costs={costs} agentCount={agents.length} />;
      case 'agents': return <AgentRegistryTab agents={agents} onAudit={handleAudit} />;
      case 'portfolio': return <PortfolioTab portfolio={portfolio} costs={costs} trades={trades} />;
      case 'bugs': return <BugTab bugSummary={bugSummary} bugs={bugs} />;
      case 'watchdog': return <WatchdogTab watchdogLogs={watchdogLogs} />;
      case 'arch': return <ArchitectureTab agents={agents} />;
      default: return null;
    }
  };

  return (
    <div className="app-container">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} systemStatus={systemStatus} wsConnected={wsConnected} />
      <div className="main-content">
        <Topbar portfolio={portfolio} systemStatus={systemStatus} agentCount={agents.length} onEvolution={handleEvolution} onAudit={handleAudit} onPause={handlePause} onResume={handleResume} />
        <div className="canvas-area" style={{ margin: '16px', borderRadius: '24px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.05)' }}>
          {renderContent()}
        </div>
        <Feed logs={feedLogs} />
      </div>
    </div>
  );
}
