/* ═══════════════════════════════════════════════════════════════
   JARVIS COMMAND CENTER — Application Logic
   ═══════════════════════════════════════════════════════════════ */

const API_BASE = window.location.origin;
let ws = null;
let currentHitlIssueId = null;

// Format currency nicely
function fmt(n) {
  if (Math.abs(n) >= 1000) return '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return '$' + n.toFixed(2);
}

// ════════════════════════════════════════════════════════════════
// NAVIGATION
// ════════════════════════════════════════════════════════════════

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const section = btn.dataset.section;
    // Update nav
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    // Update sections
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById(`section-${section}`).classList.add('active');
    // Load data for the section
    loadSectionData(section);
  });
});

function loadSectionData(section) {
  switch(section) {
    case 'overview': loadOverview(); break;
    case 'agents': loadAgents(); break;
    case 'roadmap': loadRoadmap(); break;
    case 'bugs': loadBugs(); break;
    case 'hitl': loadHitlQueue(); break;
    case 'audit': break; // loaded on demand
  }
}

// ════════════════════════════════════════════════════════════════
// DATA FETCHING
// ════════════════════════════════════════════════════════════════

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  try {
    const r = await fetch(`${API_BASE}${path}`, opts);
    return await r.json();
  } catch(e) {
    console.error(`API error: ${path}`, e);
    return null;
  }
}

// ════════════════════════════════════════════════════════════════
// OVERVIEW
// ════════════════════════════════════════════════════════════════

async function loadOverview() {
  const data = await api('/api/status');
  if (!data) return;

  const p = data.portfolio || {};
  document.getElementById('kpi-equity').textContent = fmt(p.total_equity || 0);
  document.getElementById('kpi-pnl').textContent = fmt(p.daily_pnl || 0);
  document.getElementById('kpi-cost').textContent = `$${(p.total_api_cost_today || 0).toFixed(2)}`;

  const pnlDelta = document.getElementById('kpi-pnl-delta');
  if (p.daily_pnl > 0) { pnlDelta.textContent = '▲ positive'; pnlDelta.className = 'kpi-delta positive'; }
  else if (p.daily_pnl < 0) { pnlDelta.textContent = '▼ negative'; pnlDelta.className = 'kpi-delta negative'; }
  else { pnlDelta.textContent = '—'; pnlDelta.className = 'kpi-delta neutral'; }

  const audit = data.system_audit || {};
  const readiness = Math.round((audit.readiness_score || 0) * 100);
  document.getElementById('kpi-readiness').textContent = `${readiness}%`;
  document.getElementById('readiness-bar').style.width = `${readiness}%`;

  const agents = data.agents || [];
  const activeCount = agents.filter(a => a.status === 'ACTIVE').length;
  document.getElementById('kpi-agents').textContent = `${activeCount}/${agents.length}`;

  const bugs = data.bugs || [];
  const openBugs = bugs.filter(b => b.status === 'OPEN').length;
  document.getElementById('kpi-bugs').textContent = openBugs;
  document.getElementById('kpi-bugs-label').textContent = openBugs === 0 ? 'None' : `${openBugs} open`;
  if (openBugs > 0) document.getElementById('kpi-bugs-label').className = 'kpi-delta negative';

  // Portfolio stats
  document.getElementById('stat-settled').textContent = fmt(p.settled_cash || 0);
  document.getElementById('stat-unsettled').textContent = fmt(p.unsettled_cash || 0);
  document.getElementById('stat-tranches').textContent = `${p.available_tranches || 0}/10`;
  document.getElementById('stat-drawdown').textContent = `${(p.drawdown_pct || 0).toFixed(1)}%`;
  document.getElementById('stat-model').textContent = (data.model_config || {}).current_model || 'gemini-2.5-flash';
  document.getElementById('stat-uptime').textContent = `${(data.uptime_hours || 0).toFixed(1)}h`;

  // System status
  const statusPill = document.getElementById('system-status');
  statusPill.className = `status-pill ${(data.status || 'RUNNING').toLowerCase()}`;
  statusPill.querySelector('.status-text').textContent = data.status || 'RUNNING';

  document.getElementById('phase-badge').textContent = data.current_phase || 'IDLE';

  // Render tranches
  renderTranches(p);
}

function renderTranches(portfolio) {
  const grid = document.getElementById('tranche-grid');
  grid.innerHTML = '';
  const avail = portfolio.available_tranches || 10;
  const locked = portfolio.locked_tranches || 0;
  const settling = portfolio.settling_tranches || 0;
  const trancheVal = portfolio.tranche_size || (portfolio.total_equity || 100000) / 10;
  const trancheLabel = trancheVal >= 1000 ? '$' + (trancheVal/1000).toFixed(0) + 'k' : '$' + trancheVal.toFixed(0);
  for (let i = 0; i < 10; i++) {
    const t = document.createElement('div');
    t.className = 'tranche';
    if (i < avail) { t.classList.add('available'); t.textContent = trancheLabel; }
    else if (i < avail + locked) { t.classList.add('locked'); t.textContent = '🔒'; }
    else { t.classList.add('settling'); t.textContent = '⏳'; }
    grid.appendChild(t);
  }
}

// ════════════════════════════════════════════════════════════════
// AGENTS
// ════════════════════════════════════════════════════════════════

async function loadAgents() {
  const data = await api('/api/agents');
  if (!data) return;

  const grid = document.getElementById('agent-grid');
  grid.innerHTML = '';

  (data.agents || []).forEach(agent => {
    const typeClass = (agent.type || '').toLowerCase();
    const trust = agent.trust_weight || 1.0;
    const trustPct = (trust * 100).toFixed(0);
    let trustColor = 'var(--accent-green)';
    if (trust < 0.5) trustColor = 'var(--accent-red)';
    else if (trust < 0.8) trustColor = 'var(--accent-amber)';

    const card = document.createElement('div');
    card.className = 'agent-card';
    card.onclick = () => openAgentDetail(agent.id);
    card.innerHTML = `
      <div class="agent-card-top">
        <span class="agent-name">${agent.name}</span>
        <span class="agent-role-badge ${typeClass}">${agent.type}</span>
      </div>
      <div class="agent-stats">
        <div class="agent-stat">
          <div class="agent-stat-label">Trust</div>
          <div class="agent-stat-value">${trustPct}%</div>
        </div>
        <div class="agent-stat">
          <div class="agent-stat-label">Brier</div>
          <div class="agent-stat-value">${agent.brier_score !== null ? agent.brier_score.toFixed(2) : '—'}</div>
        </div>
        <div class="agent-stat">
          <div class="agent-stat-label">Tasks</div>
          <div class="agent-stat-value">${agent.tasks_today || 0}</div>
        </div>
        <div class="agent-stat">
          <div class="agent-stat-label">Cost</div>
          <div class="agent-stat-value">$${(agent.cost_today || 0).toFixed(3)}</div>
        </div>
      </div>
      <div class="trust-bar-wrap">
        <div class="trust-bar" style="width:${trustPct}%; background:${trustColor}"></div>
      </div>
    `;
    grid.appendChild(card);
  });
}

// ════════════════════════════════════════════════════════════════
// AGENT DETAIL
// ════════════════════════════════════════════════════════════════

async function openAgentDetail(agentId) {
  const data = await api(`/api/agents/${agentId}`);
  if (!data) return;

  // Header
  document.getElementById('agent-detail-name').textContent = data.name || 'Agent';
  const badge = document.getElementById('agent-detail-type-badge');
  badge.textContent = data.type || '';
  badge.className = `agent-role-badge ${(data.type || '').toLowerCase()}`;

  // Identity
  document.getElementById('ad-role').textContent = data.role || '—';
  document.getElementById('ad-type').textContent = data.type || '—';

  const statusEl = document.getElementById('ad-status');
  statusEl.textContent = data.status || '—';
  statusEl.className = 'detail-val' + (data.status === 'ACTIVE' ? ' active' : data.status === 'EVOLVING' ? ' warning' : '');

  document.getElementById('ad-model').textContent = data.model || 'gemini-2.5-flash';

  // Metrics
  const m = data.metrics || {};
  document.getElementById('ad-trust').textContent = ((m.trust_weight || 1) * 100).toFixed(0) + '%';
  document.getElementById('ad-brier').textContent = m.brier_score !== null && m.brier_score !== undefined ? m.brier_score.toFixed(4) : '—';
  document.getElementById('ad-tasks-today').textContent = m.tasks_today || 0;
  document.getElementById('ad-tasks-all').textContent = m.tasks_alltime || 0;
  document.getElementById('ad-cost-today').textContent = '$' + (m.cost_today || 0).toFixed(4);
  document.getElementById('ad-cost-all').textContent = '$' + (m.cost_alltime || 0).toFixed(4);
  document.getElementById('ad-tokens').textContent = (m.tokens_today || 0).toLocaleString();
  document.getElementById('ad-failures').textContent = m.consecutive_failures || 0;
  document.getElementById('ad-evolutions').textContent = m.evolution_count || 0;
  document.getElementById('ad-last-activity').textContent = m.last_activity ? new Date(m.last_activity).toLocaleString() : 'Never';

  // Trust bar
  const trustPct = ((m.trust_weight || 1) * 100);
  const bar = document.getElementById('ad-trust-bar');
  bar.style.width = trustPct + '%';
  bar.style.background = trustPct < 50 ? 'var(--accent-red)' : trustPct < 80 ? 'var(--accent-amber)' : 'var(--accent-green)';

  // Skills
  const skillsEl = document.getElementById('ad-skills');
  const skills = data.skills || [];
  if (skills.length > 0) {
    skillsEl.innerHTML = skills.map(s => `<span class="skill-chip">${s}</span>`).join('');
  } else {
    skillsEl.innerHTML = '<span class="empty-inline">No skills files found</span>';
  }

  // Goals — simple markdown to HTML
  const goalsEl = document.getElementById('ad-goals');
  const goalsRaw = data.goals || '_No goals defined_';
  goalsEl.innerHTML = renderMarkdown(goalsRaw);

  // Show modal
  document.getElementById('agent-detail-modal').style.display = 'flex';
}

function closeAgentDetail() {
  document.getElementById('agent-detail-modal').style.display = 'none';
}

function renderMarkdown(md) {
  // Simple markdown → HTML for goals display
  let html = md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>');

  // Wrap consecutive <li>s in <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Paragraphs: wrap lines that aren't already in tags
  html = html.split('\n').map(line => {
    const trimmed = line.trim();
    if (!trimmed) return '';
    if (trimmed.startsWith('<')) return line;
    return `<p>${line}</p>`;
  }).join('\n');

  return html;
}

// ════════════════════════════════════════════════════════════════
// ROADMAP
// ════════════════════════════════════════════════════════════════

async function loadRoadmap() {
  const data = await api('/api/roadmap');
  const container = document.getElementById('roadmap-content');
  if (!data || !data.tasks || data.tasks.length === 0) {
    container.innerHTML = '<div class="empty-state">No roadmap tasks. System is fully caught up! 🎉</div>';
    return;
  }

  // Group by priority
  const groups = {};
  const labels = { 1: '🔴 Critical', 2: '🟠 High', 3: '🟡 Medium', 4: '🔵 Normal', 5: '⚪ Low' };
  data.tasks.forEach(t => {
    const p = t.priority || 5;
    if (!groups[p]) groups[p] = [];
    groups[p].push(t);
  });

  let html = `<div style="margin-bottom:16px;font-size:13px;color:var(--text-secondary)">
    ${data.tasks.length} tasks • ${(data.total_estimated_hours || 0).toFixed(1)} hours estimated
  </div>`;

  for (const [priority, tasks] of Object.entries(groups)) {
    html += `<div class="roadmap-group">
      <div class="roadmap-group-title">${labels[priority] || `Priority ${priority}`} (${tasks.length})</div>`;
    tasks.forEach(t => {
      html += `<div class="roadmap-item">
        <div class="roadmap-priority p${priority}"></div>
        <div class="roadmap-title">${t.title}</div>
        <span class="roadmap-category">${t.category}</span>
        <span class="roadmap-meta">${t.estimated_hours}h</span>
      </div>`;
    });
    html += '</div>';
  }

  container.innerHTML = html;
}

// ════════════════════════════════════════════════════════════════
// BUGS
// ════════════════════════════════════════════════════════════════

async function loadBugs() {
  const data = await api('/api/bugs');
  const summary = await api('/api/bugs/summary');
  const bugList = document.getElementById('bug-list');
  const bugStats = document.getElementById('bug-stats');

  // Stats
  if (summary) {
    bugStats.innerHTML = `
      <div class="bug-stat-card"><div class="bug-stat-value">${summary.total || 0}</div><div class="bug-stat-label">Total</div></div>
      <div class="bug-stat-card"><div class="bug-stat-value" style="color:var(--accent-red)">${summary.open || 0}</div><div class="bug-stat-label">Open</div></div>
      <div class="bug-stat-card"><div class="bug-stat-value" style="color:var(--accent-amber)">${summary.in_progress || 0}</div><div class="bug-stat-label">In Progress</div></div>
      <div class="bug-stat-card"><div class="bug-stat-value" style="color:var(--accent-green)">${summary.resolved || 0}</div><div class="bug-stat-label">Resolved</div></div>
    `;
  }

  // List
  const bugs = (data && data.bugs) || [];
  if (bugs.length === 0) {
    bugList.innerHTML = '<div class="empty-state">No bugs found — system healthy 🎉</div>';
    return;
  }

  bugList.innerHTML = bugs.map(b => `
    <div class="bug-item" onclick="openHitlModal('${b.id}', '${(b.title||'').replace(/'/g,"\\'")}', '${(b.description||'').replace(/'/g,"\\'")}', '${b.severity}')">
      <div class="bug-severity ${(b.severity || '').toLowerCase()}"></div>
      <div class="bug-title">${b.title || 'Untitled'}</div>
      <span class="bug-status ${(b.status || '').toLowerCase().replace('_','-')}">${b.status || 'OPEN'}</span>
    </div>
  `).join('');
}

// ════════════════════════════════════════════════════════════════
// HITL
// ════════════════════════════════════════════════════════════════

async function loadHitlQueue() {
  const data = await api('/api/hitl/queue');
  const bugs = await api('/api/bugs');
  const container = document.getElementById('hitl-queue');

  // Combine HITL queue items and open bugs
  let items = [];
  if (data && data.queue) items.push(...data.queue);
  if (bugs && bugs.bugs) items.push(...bugs.bugs.filter(b => b.status === 'OPEN'));

  if (items.length === 0) {
    container.innerHTML = '<div class="empty-state">No items pending human review</div>';
    document.getElementById('hitl-pending').textContent = '0 pending';
    return;
  }

  document.getElementById('hitl-pending').textContent = `${items.length} pending`;

  container.innerHTML = items.map(item => `
    <div class="hitl-item">
      <div class="bug-severity ${(item.severity || 'medium').toLowerCase()}"></div>
      <div class="hitl-item-content">
        <div class="hitl-item-title">${item.title || 'Issue'}</div>
        <div class="hitl-item-desc">${item.description || ''}</div>
      </div>
      <div class="hitl-item-actions">
        <button class="action-btn success" onclick="quickHitl('${item.id}','APPROVE')" title="Approve">✅</button>
        <button class="action-btn danger" onclick="quickHitl('${item.id}','REJECT')" title="Reject">❌</button>
        <button class="action-btn warning" onclick="quickHitl('${item.id}','ESCALATE')" title="Escalate">⬆</button>
        <button class="action-btn" onclick="openHitlModal('${item.id}','${(item.title||'').replace(/'/g,"\\'")}','${(item.description||'').replace(/'/g,"\\'")}','${item.severity}')" title="Details">⚙️</button>
      </div>
    </div>
  `).join('');
}

async function quickHitl(issueId, action) {
  await api('/api/hitl/action', 'POST', { issue_id: issueId, action });
  loadHitlQueue();
  loadBugs();
  loadOverview();
}

// ════════════════════════════════════════════════════════════════
// MODALS
// ════════════════════════════════════════════════════════════════

function openCreateIssue() {
  document.getElementById('create-issue-modal').style.display = 'flex';
}
function closeModal() {
  document.getElementById('create-issue-modal').style.display = 'none';
}

async function submitIssue() {
  const title = document.getElementById('issue-title').value;
  const desc = document.getElementById('issue-desc').value;
  const severity = document.getElementById('issue-severity').value;
  if (!title) return;
  await api('/api/hitl/create', 'POST', { title, description: desc, severity });
  closeModal();
  document.getElementById('issue-title').value = '';
  document.getElementById('issue-desc').value = '';
  loadBugs();
  loadHitlQueue();
  loadOverview();
}

function openHitlModal(issueId, title, desc, severity) {
  currentHitlIssueId = issueId;
  document.getElementById('hitl-issue-detail').innerHTML = `
    <div style="margin-bottom:12px">
      <div class="bug-severity ${(severity||'').toLowerCase()}" style="display:inline-block;vertical-align:middle;margin-right:8px"></div>
      <strong>${title}</strong>
    </div>
    <p style="color:var(--text-secondary);font-size:13px">${desc || 'No description'}</p>
  `;
  document.getElementById('hitl-modal').style.display = 'flex';
}
function closeHitlModal() {
  document.getElementById('hitl-modal').style.display = 'none';
  currentHitlIssueId = null;
}

async function submitHitlAction(action) {
  if (!currentHitlIssueId) return;
  const notes = document.getElementById('hitl-notes').value;
  const priority = document.getElementById('hitl-priority').value || undefined;
  await api('/api/hitl/action', 'POST', {
    issue_id: currentHitlIssueId,
    action,
    notes: notes || undefined,
    priority,
  });
  closeHitlModal();
  document.getElementById('hitl-notes').value = '';
  loadHitlQueue();
  loadBugs();
  loadOverview();
}

// ════════════════════════════════════════════════════════════════
// CONTROL ACTIONS
// ════════════════════════════════════════════════════════════════

async function pauseTrading() {
  await api('/api/control/pause', 'POST');
  loadOverview();
}
async function resumeTrading() {
  await api('/api/control/resume', 'POST');
  loadOverview();
}
async function triggerHCFReset() {
  if (confirm('Reset the Halt-and-Catch-Fire protocol?')) {
    await api('/api/control/hcf-reset', 'POST');
    loadOverview();
  }
}
async function forceEvolution() {
  await api('/api/control/force-evolution', 'POST');
  loadOverview();
}
async function forceAudit() {
  await api('/api/control/force-audit', 'POST');
  loadOverview();
  runFullAudit();
}

async function runFullAudit() {
  const container = document.getElementById('audit-content');
  container.innerHTML = '<div class="empty-state">Running audit...</div>';
  const data = await api('/api/audit');
  if (!data) { container.innerHTML = '<div class="empty-state">Audit failed</div>'; return; }

  let html = `
    <div class="kpi-row" style="margin-bottom:20px">
      <div class="kpi-card"><div class="kpi-label">Readiness</div><div class="kpi-value">${Math.round((data.readiness_score||0)*100)}%</div></div>
      <div class="kpi-card"><div class="kpi-label">Files</div><div class="kpi-value">${data.total_files || 0}</div></div>
      <div class="kpi-card"><div class="kpi-label">Lines</div><div class="kpi-value">${(data.total_lines||0).toLocaleString()}</div></div>
      <div class="kpi-card"><div class="kpi-label">Agents w/ Skills</div><div class="kpi-value">${data.agents_with_skills || 0}</div></div>
      <div class="kpi-card"><div class="kpi-label">Agents w/ Goals</div><div class="kpi-value">${data.agents_with_goals || 0}</div></div>
      <div class="kpi-card"><div class="kpi-label">Test Files</div><div class="kpi-value">${data.test_count || 0}</div></div>
    </div>
  `;

  const findings = data.findings || [];
  if (findings.length > 0) {
    html += '<h3 style="margin-bottom:12px;font-size:14px">Findings</h3>';
    const sevColors = { CRITICAL: 'danger', HIGH: 'warning', MEDIUM: '', LOW: '' };
    findings.forEach(f => {
      html += `<div class="audit-finding">
        <span class="audit-finding-severity badge ${sevColors[f.severity] || ''}">${f.severity}</span>
        <div>
          <span style="font-weight:600;font-size:12px">[${f.category}]</span>
          <code style="font-size:11px;color:var(--text-muted);margin:0 6px">${f.location}</code>
          <span style="font-size:12px">${f.description}</span>
        </div>
      </div>`;
    });
  } else {
    html += '<div class="empty-state">No findings — system is clean! 🎉</div>';
  }

  container.innerHTML = html;
}

// ════════════════════════════════════════════════════════════════
// WEBSOCKET
// ════════════════════════════════════════════════════════════════

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'status_update') {
        const d = msg.data;
        document.getElementById('system-status').className = `status-pill ${(d.status||'running').toLowerCase()}`;
        document.getElementById('system-status').querySelector('.status-text').textContent = d.status || 'RUNNING';
        document.getElementById('phase-badge').textContent = d.phase || 'IDLE';
      }
    } catch(err) {}
  };
  ws.onclose = () => setTimeout(connectWebSocket, 3000);
  ws.onerror = () => ws.close();
}

// ════════════════════════════════════════════════════════════════
// INIT
// ════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
  loadOverview();
  connectWebSocket();
  // Auto-refresh every 30s
  setInterval(loadOverview, 30000);
});

// Pause/Resume buttons
document.getElementById('btn-pause').addEventListener('click', async () => {
  await pauseTrading();
  document.getElementById('btn-pause').style.display = 'none';
  document.getElementById('btn-resume').style.display = 'flex';
});
document.getElementById('btn-resume').addEventListener('click', async () => {
  await resumeTrading();
  document.getElementById('btn-resume').style.display = 'none';
  document.getElementById('btn-pause').style.display = 'flex';
});
