/**
 * Jarvis Command Center — API Client
 * 
 * Centralized client for fetching real data from the Jarvis FastAPI backend.
 * All dashboard components should use these functions instead of hardcoded data.
 * 
 * Backend runs at localhost:8000 (configurable via VITE_API_URL env var).
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function apiFetch(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPost(path, body = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API POST ${path} failed: ${res.status}`);
  return res.json();
}

// ── Status & Health ──────────────────────────────────────────────

export async function fetchSystemStatus() {
  return apiFetch('/api/status');
}

export async function fetchHealth() {
  return apiFetch('/health');
}

// ── Portfolio (Live from Alpaca) ─────────────────────────────────

export async function fetchPortfolio() {
  return apiFetch('/api/portfolio');
}

export async function fetchPortfolioHistory() {
  return apiFetch('/api/portfolio/history');
}

// ── Agents ───────────────────────────────────────────────────────

export async function fetchAgents() {
  return apiFetch('/api/agents');
}

export async function fetchAgentDetail(agentId) {
  return apiFetch(`/api/agents/${agentId}`);
}

export async function fetchAgentHierarchy() {
  return apiFetch('/api/agents/hierarchy');
}

// ── Trades ───────────────────────────────────────────────────────

export async function fetchTrades() {
  return apiFetch('/api/trades');
}

// ── Bugs ─────────────────────────────────────────────────────────

export async function fetchBugs() {
  return apiFetch('/api/bugs');
}

export async function fetchBugSummary() {
  return apiFetch('/api/bugs/summary');
}

export async function fetchBugDetail(bugId) {
  return apiFetch(`/api/bugs/${bugId}`);
}

// ── Evolution & Roadmap ──────────────────────────────────────────

export async function fetchEvolution() {
  return apiFetch('/api/evolution');
}

export async function fetchRoadmap() {
  return apiFetch('/api/roadmap');
}

// ── Costs ────────────────────────────────────────────────────────

export async function fetchCosts() {
  return apiFetch('/api/costs');
}

// ── Velocity & Audit ─────────────────────────────────────────────

export async function fetchVelocity() {
  return apiFetch('/api/velocity');
}

export async function fetchAudit() {
  return apiFetch('/api/audit');
}

// ── Watchdog ─────────────────────────────────────────────────────

export async function fetchWatchdog() {
  return apiFetch('/api/watchdog');
}

// ── HITL ─────────────────────────────────────────────────────────

export async function fetchHITLQueue() {
  return apiFetch('/api/hitl/queue');
}

export async function postHITLAction(issueId, action, notes) {
  return apiPost('/api/hitl/action', { issue_id: issueId, action, notes });
}

// ── Control Actions ──────────────────────────────────────────────

export async function pauseSystem() {
  return apiPost('/api/control/pause');
}

export async function resumeSystem() {
  return apiPost('/api/control/resume');
}

export async function forceEvolution() {
  return apiPost('/api/control/force-evolution');
}

export async function forceAudit() {
  return apiPost('/api/control/force-audit');
}

export async function resetHCF() {
  return apiPost('/api/control/hcf-reset');
}

// ── WebSocket ────────────────────────────────────────────────────

export function connectWebSocket(onMessage) {
  const wsUrl = API_BASE.replace('http', 'ws') + '/ws';
  const ws = new WebSocket(wsUrl);
  
  ws.onopen = () => console.log('[WS] Connected to Jarvis backend');
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.warn('[WS] Parse error:', e);
    }
  };
  ws.onerror = (err) => console.warn('[WS] Error:', err);
  ws.onclose = () => {
    console.log('[WS] Disconnected. Reconnecting in 5s...');
    setTimeout(() => connectWebSocket(onMessage), 5000);
  };
  
  return ws;
}
