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
    case 'architecture': loadArchitecture(); break;
    case 'watchdog': loadWatchdog(); break;
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

  const severityColors = {
    CRITICAL: '#F87171', HIGH: '#FB923C', MEDIUM: '#FBBF24', LOW: '#60A5FA'
  };

  bugList.innerHTML = bugs.map(b => {
    const sevColor = severityColors[b.severity] || severityColors.MEDIUM;
    const statusClass = (b.status || '').toLowerCase().replace('_', '-');
    const ago = timeAgo(b.created_at);
    const source = b.source ? `<span class="bug-source">via ${b.source}</span>` : '';
    const sevLabel = `<span class="bug-sev-label" style="color:${sevColor}">${b.severity || 'MEDIUM'}</span>`;

    return `
      <div class="bug-item clickable" onclick="openBugDetail('${b.id}')">
        <div class="bug-severity" style="background:${sevColor};box-shadow:0 0 8px ${sevColor}"></div>
        <div class="bug-info">
          <div class="bug-title">${b.title || 'Untitled'}</div>
          <div class="bug-meta-row">${ago ? `<span class="bug-ago">${ago}</span>` : ''}${source}${sevLabel}</div>
        </div>
        <span class="bug-status ${statusClass}">${b.status || 'OPEN'}</span>
      </div>
    `;
  }).join('');
}

// ── Bug Detail Modal ────────────────────────────────────────────

function formatDateFull(iso) {
  if (!iso) return null;
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })
      + ' at ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  } catch(e) { return iso; }
}

function timeAgo(iso) {
  if (!iso) return '';
  try {
    const now = new Date();
    const then = new Date(iso);
    const diffMs = now - then;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs}h ago`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays}d ago`;
  } catch(e) { return ''; }
}

function calcDuration(created, resolved) {
  if (!created || !resolved) return null;
  try {
    const c = new Date(created);
    const r = new Date(resolved);
    const diffMs = r - c;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 60) return `${diffMins} minutes`;
    const diffHrs = Math.floor(diffMins / 60);
    if (diffHrs < 24) return `${diffHrs} hours`;
    const diffDays = Math.floor(diffHrs / 24);
    return `${diffDays} days`;
  } catch(e) { return null; }
}

async function openBugDetail(bugId) {
  const bug = await api(`/api/bugs/${bugId}`);
  if (!bug) return;

  const severityStyles = {
    CRITICAL: { bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.4)', text: '#F87171' },
    HIGH:     { bg: 'rgba(249,115,22,0.15)', border: 'rgba(249,115,22,0.4)', text: '#FB923C' },
    MEDIUM:   { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.4)', text: '#FBBF24' },
    LOW:      { bg: 'rgba(59,130,246,0.15)', border: 'rgba(59,130,246,0.4)', text: '#60A5FA' },
  };
  const statusStyles = {
    OPEN:        { bg: 'rgba(239,68,68,0.15)', border: 'rgba(239,68,68,0.4)', text: '#F87171', icon: '🔴' },
    IN_PROGRESS: { bg: 'rgba(245,158,11,0.15)', border: 'rgba(245,158,11,0.4)', text: '#FBBF24', icon: '🟡' },
    RESOLVED:    { bg: 'rgba(16,185,129,0.15)', border: 'rgba(16,185,129,0.4)', text: '#34D399', icon: '✅' },
    WONT_FIX:    { bg: 'rgba(107,114,128,0.15)', border: 'rgba(107,114,128,0.4)', text: '#9CA3AF', icon: '⏭️' },
    DEFERRED:    { bg: 'rgba(139,92,246,0.15)', border: 'rgba(139,92,246,0.4)', text: '#A78BFA', icon: '⏸️' },
  };

  const sev = severityStyles[bug.severity] || severityStyles.MEDIUM;
  const stat = statusStyles[bug.status] || statusStyles.OPEN;
  const isAuto = (bug.title || '').startsWith('[Auto]') || bug.source === 'bug_scanner' || bug.source === 'process_monitor';

  // Badges
  let badges = `
    <span class="detail-badge" style="background:${sev.bg};border:1px solid ${sev.border};color:${sev.text}">${bug.severity}</span>
    <span class="detail-badge" style="background:${stat.bg};border:1px solid ${stat.border};color:${stat.text}">${stat.icon} ${bug.status}</span>
  `;
  if (isAuto) {
    badges += `<span class="detail-badge" style="background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.3);color:#A78BFA">🤖 Auto-filed</span>`;
  }
  document.getElementById('bug-detail-badges').innerHTML = badges;

  // Title + filed date
  document.getElementById('bug-detail-title').textContent = bug.title || 'Untitled';
  const filedDate = formatDateFull(bug.created_at);
  const agoStr = timeAgo(bug.created_at);
  document.getElementById('bug-detail-filed').innerHTML = filedDate
    ? `Filed ${filedDate} <span style="color:var(--text-muted)">(${agoStr})</span>`
    : '';

  // Timeline
  let timelineHtml = `
    <div class="timeline-card">
      <div class="timeline-label">Created</div>
      <div class="timeline-value">${formatDateFull(bug.created_at) || '—'}</div>
    </div>
  `;
  if (bug.started_at) {
    timelineHtml += `
      <div class="timeline-card">
        <div class="timeline-label">Work Started</div>
        <div class="timeline-value">${formatDateFull(bug.started_at)}</div>
      </div>
    `;
  }
  if (bug.resolved_at) {
    timelineHtml += `
      <div class="timeline-card">
        <div class="timeline-label">Resolved</div>
        <div class="timeline-value" style="color:var(--accent-green)">${formatDateFull(bug.resolved_at)}</div>
      </div>
    `;
  }
  const dur = calcDuration(bug.created_at, bug.resolved_at);
  if (dur) {
    timelineHtml += `
      <div class="timeline-card">
        <div class="timeline-label">Resolution Time</div>
        <div class="timeline-value" style="color:var(--accent-cyan)">${dur}</div>
      </div>
    `;
  }
  document.getElementById('bug-detail-timeline').innerHTML = timelineHtml;

  // Description
  const descSection = document.getElementById('bug-detail-desc-section');
  if (bug.description) {
    descSection.style.display = 'block';
    document.getElementById('bug-detail-desc').textContent = bug.description;
  } else {
    descSection.style.display = 'none';
  }

  // Metadata
  document.getElementById('bug-detail-meta').innerHTML = `
    <div class="meta-card">
      <div class="meta-label">Source</div>
      <div class="meta-value">${bug.source || 'Manual'}</div>
    </div>
    <div class="meta-card">
      <div class="meta-label">Assigned To</div>
      <div class="meta-value">${bug.assigned_to || 'Unassigned'}</div>
    </div>
  `;

  // PR link
  const prSection = document.getElementById('bug-detail-pr-section');
  if (bug.pr_url) {
    prSection.style.display = 'block';
    const prLink = document.getElementById('bug-detail-pr-link');
    prLink.href = bug.pr_url;
    prLink.textContent = '🔗 ' + bug.pr_url;
  } else {
    prSection.style.display = 'none';
  }

  // Worker error
  const errSection = document.getElementById('bug-detail-error-section');
  if (bug.worker_error) {
    errSection.style.display = 'block';
    document.getElementById('bug-detail-error').textContent = bug.worker_error;
  } else {
    errSection.style.display = 'none';
  }

  // Bug ID
  document.getElementById('bug-detail-id').textContent = 'ID: ' + bug.id;

  // Show modal
  document.getElementById('bug-detail-modal').style.display = 'flex';
}

function closeBugDetail() {
  document.getElementById('bug-detail-modal').style.display = 'none';
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

// ════════════════════════════════════════════════════════════════
// ARCHITECTURE (vis.js)
// ════════════════════════════════════════════════════════════════

let archNetwork = null;

async function loadArchitecture() {
  const data = await api('/api/agents');
  if (!data || !data.agents) return;
  const agents = data.agents;
  
  document.getElementById('arch-agent-count').textContent = `${agents.length} active agents`;

  // Create nodes
  const nodes = new vis.DataSet(agents.map(a => {
    // Determine color based on type
    let color = { background: '#1e293b', border: '#475569' };
    if (a.role === 'MASTER') color = { background: '#2563eb', border: '#60a5fa' };
    else if (a.type === 'EXECUTIVE') color = { background: '#7c3aed', border: '#a78bfa' };
    else if (a.type === 'MANAGER') color = { background: '#059669', border: '#34d399' };
    else if (a.type === 'ANALYST') color = { background: '#d97706', border: '#fbbf24' };

    return {
      id: a.id,
      label: a.name + '\\n(' + (a.role || 'Agent') + ')',
      title: 'Click to view details',
      color: color,
      shape: 'box',
      font: { color: '#f0f3f6', face: 'Inter' },
      borderWidth: 2,
      shadow: true
    };
  }));

  // Create edges: Executive -> Manager -> Specialist/Analyst
  const edgesData = [];
  const master = agents.find(a => a.role === 'MASTER');
  const executives = agents.filter(a => a.type === 'EXECUTIVE' && a.role !== 'MASTER');
  const managers = agents.filter(a => a.type === 'MANAGER');
  const others = agents.filter(a => ['ANALYST', 'SPECIALIST'].includes(a.type) && a.role !== 'MASTER');

  if (master) {
    executives.forEach(e => edgesData.push({ from: master.id, to: e.id, arrows: 'to', color: '#475569' }));
  }
  
  executives.forEach(e => {
      managers.forEach(m => {
          if ((e.division === m.division) || (!e.division && !m.division)) {
              edgesData.push({ from: e.id, to: m.id, arrows: 'to', color: '#475569' });
          }
      });
  });

  managers.forEach(m => {
      others.forEach(o => {
          if ((m.division === o.division) || (!m.division && !o.division)) {
              edgesData.push({ from: m.id, to: o.id, arrows: 'to', color: '#475569', dashes: true });
          }
      });
  });

  const edges = new vis.DataSet(edgesData);
  const container = document.getElementById('architecture-network');
  const networkData = { nodes, edges };
  const options = {
    layout: { hierarchical: { direction: 'UD', sortMethod: 'directed', nodeSpacing: 150, treeSpacing: 200 } },
    physics: false,
    interaction: { hover: true, tooltipDelay: 200 }
  };

  if (archNetwork) archNetwork.destroy();
  archNetwork = new vis.Network(container, networkData, options);

  // Click event to drill down
  archNetwork.on("click", function (params) {
    if (params.nodes.length > 0) {
      openAgentDetail(params.nodes[0]);
    }
  });
}

// ════════════════════════════════════════════════════════════════
// WATCHDOG
// ════════════════════════════════════════════════════════════════

async function loadWatchdog() {
  const data = await api('/api/watchdog');
  const container = document.getElementById('watchdog-logs');
  
  if (!data || !data.logs || data.logs.length === 0) {
    container.innerHTML = '<div class="empty-state">No watchdog logs found.</div>';
    return;
  }
  
  const logsHtml = data.logs.map(l => {
      let colorClass = '';
      if (l.includes('ISSUES FOUND') || l.includes('❌') || l.includes('Error') || l.includes('failed')) colorClass = 'log-error';
      else if (l.includes('⚠️')) colorClass = 'log-warning';
      else if (l.includes('✅')) colorClass = 'log-success';
      
      const escaped = l.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return `<div class="log-line ${colorClass}">${escaped}</div>`;
  }).join('');

  container.innerHTML = logsHtml;
  container.scrollTop = container.scrollHeight;
}
