/**
 * SelfEvolve Dashboard — Interactive Application Logic
 *
 * Handles navigation, data fetching, WebSocket real-time updates,
 * owner chat, and system controls.
 */

const API_BASE = window.location.origin;
const WS_URL = `ws://${window.location.host}/ws`;

// ════════════════════════════════════════════════════════════════════
// NAVIGATION
// ════════════════════════════════════════════════════════════════════

document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const section = link.dataset.section;

        // Update active nav
        document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
        link.classList.add('active');

        // Show section
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        const target = document.getElementById(`section-${section}`);
        if (target) target.classList.add('active');

        // Update page title
        const titles = {
            overview: 'Command Center',
            agents: 'Agent Registry',
            trades: 'Trade Ledger',
            evolution: 'Evolution Timeline',
            bugs: 'Bug Tracker',
            audit: 'Audit Trail',
            costs: 'Cost Center',
            chat: 'Owner Chat'
        };
        document.getElementById('page-title').textContent = titles[section] || 'Dashboard';
    });
});

// ════════════════════════════════════════════════════════════════════
// DATA FETCHING
// ════════════════════════════════════════════════════════════════════

async function fetchData(endpoint) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.warn(`Failed to fetch ${endpoint}:`, error.message);
        return null;
    }
}

async function refreshDashboard() {
    const [status, portfolio, agents, trades, bugs, costs] = await Promise.all([
        fetchData('/api/status'),
        fetchData('/api/portfolio'),
        fetchData('/api/agents'),
        fetchData('/api/trades'),
        fetchData('/api/bugs/summary'),
        fetchData('/api/costs'),
    ]);

    if (portfolio) updatePortfolioUI(portfolio);
    if (agents) updateAgentsUI(agents);
    if (trades) updateTradesUI(trades);
    if (bugs) updateBugsUI(bugs);
    if (costs) updateCostsUI(costs);
    if (status) updateSystemStatus(status);

    renderTranches();
}

// ════════════════════════════════════════════════════════════════════
// UI UPDATE FUNCTIONS
// ════════════════════════════════════════════════════════════════════

function updatePortfolioUI(data) {
    const equity = data.total_equity || 100;
    const pnl = data.daily_pnl || 0;
    const apiCost = data.total_api_cost_today || 0;
    const netPnl = pnl - apiCost;
    const drawdown = data.drawdown_pct || 0;

    document.getElementById('equity-value').textContent = `$${equity.toFixed(2)}`;
    document.getElementById('pnl-value').textContent = `$${netPnl.toFixed(2)}`;
    document.getElementById('api-cost-value').textContent = `$${apiCost.toFixed(4)}`;
    document.getElementById('drawdown-value').textContent = `${drawdown.toFixed(2)}%`;
    document.getElementById('settled-cash').textContent = `$${(data.settled_cash || 100).toFixed(2)}`;
    document.getElementById('unsettled-cash').textContent = `$${(data.unsettled_cash || 0).toFixed(2)}`;

    // Color the P&L value
    const pnlEl = document.getElementById('pnl-value');
    const changeEl = document.getElementById('pnl-change');
    if (netPnl > 0) {
        pnlEl.style.color = 'var(--accent-green)';
        changeEl.className = 'kpi-change positive';
    } else if (netPnl < 0) {
        pnlEl.style.color = 'var(--accent-red)';
        changeEl.className = 'kpi-change negative';
    }
}

function updateAgentsUI(data) {
    const agents = data.agents || [];
    document.getElementById('agents-count').textContent = agents.length;
    const activeCount = agents.filter(a => a.status === 'ACTIVE').length;
    document.getElementById('agents-status').textContent = `${activeCount} active`;

    if (agents.length === 0) return;

    const grid = document.getElementById('agents-grid');
    grid.innerHTML = agents.map(agent => `
        <div class="agent-card">
            <div class="agent-header">
                <div>
                    <div class="agent-name">${agent.agent_name || agent.name || 'Unknown'}</div>
                    <div class="agent-role">${agent.agent_role || agent.role || ''}</div>
                </div>
                <span class="badge ${agent.status === 'ACTIVE' ? 'badge-live' : 'badge-paper'}">${agent.status || 'IDLE'}</span>
            </div>
            <div class="agent-metrics">
                <div class="agent-metric">
                    <div class="metric-label">Trust</div>
                    <div class="metric-value">${(agent.trust_weight || 1.0).toFixed(2)}</div>
                </div>
                <div class="agent-metric">
                    <div class="metric-label">Brier</div>
                    <div class="metric-value">${(agent.brier_score || 0.5).toFixed(3)}</div>
                </div>
                <div class="agent-metric">
                    <div class="metric-label">Cost</div>
                    <div class="metric-value">$${(agent.total_cost || 0).toFixed(4)}</div>
                </div>
                <div class="agent-metric">
                    <div class="metric-label">Version</div>
                    <div class="metric-value">v${agent.version || 1}</div>
                </div>
            </div>
        </div>
    `).join('');
}

function updateTradesUI(data) {
    const trades = data.trades || [];
    document.getElementById('trades-count').textContent = trades.length;

    if (trades.length > 0) {
        const wins = trades.filter(t => (t.realized_pnl || 0) > 0).length;
        const winRate = ((wins / trades.length) * 100).toFixed(0);
        document.getElementById('trades-winrate').textContent = `Win Rate: ${winRate}%`;

        const tbody = document.getElementById('trades-tbody');
        tbody.innerHTML = trades.map(t => `
            <tr>
                <td>${new Date(t.entry_time || t.created_at).toLocaleTimeString()}</td>
                <td><strong>${t.ticker}</strong></td>
                <td>${t.side}</td>
                <td>$${(t.notional || 0).toFixed(2)}</td>
                <td>${(t.conviction_score || 0).toFixed(1)}</td>
                <td style="color: ${(t.realized_pnl || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}">
                    $${(t.realized_pnl || 0).toFixed(2)}
                </td>
                <td>${t.status}</td>
            </tr>
        `).join('');
    }
}

function updateBugsUI(data) {
    // Update bugs KPI if visible
}

function updateCostsUI(data) {
    if (data) {
        document.getElementById('total-api-spend').textContent = `$${(data.total_cost_today || 0).toFixed(4)}`;
        document.getElementById('budget-remaining').textContent = `$${(1.0 - (data.total_cost_today || 0)).toFixed(4)}`;
    }
}

function updateSystemStatus(data) {
    const statusBadge = document.getElementById('system-status-badge');
    if (data.status === 'RUNNING') {
        statusBadge.textContent = 'RUNNING';
        statusBadge.className = 'badge badge-live';
    } else if (data.status === 'PAUSED') {
        statusBadge.textContent = 'PAUSED';
        statusBadge.className = 'badge badge-paper';
    } else if (data.hcf_active) {
        statusBadge.textContent = 'HCF';
        statusBadge.className = 'badge badge-danger';
    }
}

function renderTranches() {
    const grid = document.getElementById('tranche-grid');
    grid.innerHTML = '';
    for (let i = 0; i < 10; i++) {
        const cell = document.createElement('div');
        cell.className = 'tranche-cell available';
        cell.textContent = `$10`;
        cell.title = `Tranche ${i + 1}: Available`;
        grid.appendChild(cell);
    }
}

// ════════════════════════════════════════════════════════════════════
// WEBSOCKET REAL-TIME
// ════════════════════════════════════════════════════════════════════

let ws = null;

function connectWebSocket() {
    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log('WebSocket connected');
            addActivity('Connected to real-time feed');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'status_update' && data.data) {
                    if (data.data.portfolio) updatePortfolioUI(data.data.portfolio);
                }
            } catch (e) {
                console.warn('WebSocket parse error:', e);
            }
        };

        ws.onclose = () => {
            console.log('WebSocket disconnected, reconnecting in 5s...');
            setTimeout(connectWebSocket, 5000);
        };

        ws.onerror = () => {
            ws.close();
        };
    } catch (e) {
        setTimeout(connectWebSocket, 5000);
    }
}

// ════════════════════════════════════════════════════════════════════
// CHAT
// ════════════════════════════════════════════════════════════════════

const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const chatMessages = document.getElementById('chat-messages');

async function sendChatMessage() {
    const message = chatInput.value.trim();
    if (!message) return;

    // Add user message
    appendChatMessage('user', message);
    chatInput.value = '';

    // Send to API
    try {
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });
        const data = await response.json();
        appendChatMessage('system', data.response || 'No response received.');
    } catch (error) {
        appendChatMessage('system', `Error: ${error.message}`);
    }
}

function appendChatMessage(type, text) {
    const div = document.createElement('div');
    div.className = `chat-message ${type}`;
    div.innerHTML = `<div class="chat-bubble">${escapeHtml(text)}</div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatSend.addEventListener('click', sendChatMessage);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendChatMessage();
});

// ════════════════════════════════════════════════════════════════════
// CONTROLS
// ════════════════════════════════════════════════════════════════════

document.getElementById('btn-refresh').addEventListener('click', refreshDashboard);

document.getElementById('btn-pause').addEventListener('click', async () => {
    const btn = document.getElementById('btn-pause');
    if (btn.textContent.includes('Pause')) {
        await fetch(`${API_BASE}/api/control/pause`, { method: 'POST' });
        btn.innerHTML = '▶ Resume';
        btn.className = 'btn btn-primary';
        addActivity('Trading PAUSED by owner');
    } else {
        await fetch(`${API_BASE}/api/control/resume`, { method: 'POST' });
        btn.innerHTML = '⏸ Pause';
        btn.className = 'btn btn-warning';
        addActivity('Trading RESUMED by owner');
    }
});

document.getElementById('btn-hcf').addEventListener('click', async () => {
    if (confirm('⚠️ ACTIVATE HALT-AND-CATCH-FIRE PROTOCOL?\n\nThis will:\n1. Cancel ALL open orders\n2. Set tight trailing stops\n3. Freeze all new order submission\n\nRequires manual reset.')) {
        await fetch(`${API_BASE}/api/control/hcf-reset`, { method: 'POST' });
        addActivity('🚨 HCF PROTOCOL ACTIVATED by owner');
    }
});

// ════════════════════════════════════════════════════════════════════
// UTILITIES
// ════════════════════════════════════════════════════════════════════

function addActivity(text) {
    const feed = document.getElementById('activity-feed');
    const item = document.createElement('div');
    item.className = 'activity-item';
    item.innerHTML = `
        <span class="activity-time">${new Date().toLocaleTimeString()}</span>
        <span class="activity-text">${escapeHtml(text)}</span>
    `;
    feed.prepend(item);
    if (feed.children.length > 50) feed.lastChild.remove();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ════════════════════════════════════════════════════════════════════
// INITIALIZATION
// ════════════════════════════════════════════════════════════════════

renderTranches();
refreshDashboard();
connectWebSocket();

// Auto-refresh every 30 seconds
setInterval(refreshDashboard, 30000);

addActivity('Dashboard loaded — connecting to SelfEvolve core...');
