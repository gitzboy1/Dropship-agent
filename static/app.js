let profitChart = null;
let budgetChart = null;
let currentSession = null;
let currentUser = null;
let currentWorkspace = null;
let currentTasks = [];
let currentDashboard = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initCharts();
    loadSessionState();
});

function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(button => {
        button.addEventListener('click', () => switchTab(button.dataset.tab));
    });
}

function switchTab(name) {
    document.querySelectorAll('.tab-btn').forEach(button => {
        button.classList.toggle('active', button.dataset.tab === name);
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `tab-${name}`);
    });
    if (name === 'history') {
        loadHistory();
    }
}

function escapeHtml(value) {
    return (value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function formatCurrency(value) {
    return `Rs ${(value || 0).toLocaleString()}`;
}

function formatTime(value) {
    if (!value) return 'Now';
    return new Date(value).toLocaleString();
}

async function loadSessionState() {
    try {
        const res = await fetch('/api/session');
        const data = await res.json();
        currentSession = data.session || null;
        renderAuthState(data.user, data.workspace);
        renderSessionState(data.session);
        renderConversation(data.session ? data.session.conversation || [] : []);
        renderActionLog(data.session ? data.session.actions || [] : []);
        updateProductsGrid(data.session ? data.session.products_found || [] : []);
        updateDbBadge(data.db_connected);
        loadHistory();

        if (data.authenticated) {
            await Promise.all([loadTasks(), loadDashboard(), loadAudit()]);
        } else {
            renderGuestWorkspace();
        }
    } catch (error) {
        updateDbBadge(false, 'Offline-ready');
    }
}

function updateDbBadge(dbConnected, label) {
    const badge = document.getElementById('dbBadge');
    badge.textContent = label || (dbConnected ? 'DB connected' : 'Local-first');
    badge.style.color = dbConnected ? 'var(--success)' : 'var(--warning)';
}

function renderAuthState(user, workspace) {
    currentUser = user || null;
    currentWorkspace = workspace || null;
    document.getElementById('authStatus').textContent = user ? `Signed in as ${user.full_name}` : 'Local guest mode';
    document.getElementById('workspaceChip').textContent = workspace ? workspace.name : 'Guest Workspace';
    document.getElementById('workspaceMeta').textContent = workspace
        ? `${workspace.country} • ${workspace.niche || 'General niche'} • Stage: ${workspace.store_stage}`
        : 'Sign in to unlock saved workspaces, audit trails, and task tracking.';
}

function renderSessionState(session) {
    const budget = session?.budget || 0;
    const spent = session?.spent || 0;
    const actions = session?.actions?.length || 0;
    const products = session?.products_found?.length || 0;

    document.getElementById('budgetNum').textContent = formatCurrency(budget);
    document.getElementById('spentNum').textContent = formatCurrency(spent);
    document.getElementById('productsFound').textContent = products;
    document.getElementById('actionsCount').textContent = actions;
    document.getElementById('budgetFill').style.width = budget > 0 ? `${Math.min((spent / budget) * 100, 100)}%` : '0%';
    document.getElementById('workspaceName').textContent = currentWorkspace ? currentWorkspace.name : 'Session Workspace';
}

function renderConversation(messages) {
    const container = document.getElementById('chatContainer');
    if (!messages || messages.length === 0) {
        container.innerHTML = `
            <div class="welcome-card">
                <p class="eyebrow">Ready to Operate</p>
                <h3>Use this like mission control, not just a chat box.</h3>
                <p>Launch market scans, create tasks, inspect the queue, and keep a living workspace state while the assistant works with you.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = messages.map(message => {
        const isUser = message.role === 'user';
        return `
            <div class="message-card ${isUser ? 'user' : 'agent'}">
                <div class="message-meta">
                    <span class="agent-chip">${isUser ? 'You' : (message.agent || 'assistant')}</span>
                    <span>${formatTime(message.time)}</span>
                </div>
                <div class="message-body">${escapeHtml(message.content || '')}</div>
            </div>
        `;
    }).join('');
    container.scrollTop = container.scrollHeight;
}

function appendMessage(role, content, agent = 'general') {
    const container = document.getElementById('chatContainer');
    const welcome = container.querySelector('.welcome-card');
    if (welcome) {
        welcome.remove();
    }
    const card = document.createElement('div');
    card.className = `message-card ${role === 'user' ? 'user' : 'agent'}`;
    card.innerHTML = `
        <div class="message-meta">
            <span class="agent-chip">${role === 'user' ? 'You' : agent}</span>
            <span>${formatTime(new Date().toISOString())}</span>
        </div>
        <div class="message-body">${escapeHtml(content)}</div>
    `;
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
}

function showTyping() {
    const container = document.getElementById('chatContainer');
    const typing = document.createElement('div');
    typing.className = 'message-card agent typing-card';
    typing.id = 'typingIndicator';
    typing.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
    `;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
}

function hideTyping() {
    document.getElementById('typingIndicator')?.remove();
}

async function sendMessage() {
    const input = document.getElementById('msgInput');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    appendMessage('user', message);
    showTyping();

    try {
        const res = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({message})
        });
        const data = await res.json();
        hideTyping();
        document.getElementById('currentAgent').textContent = `${capitalize(data.agent_type || 'general')} Agent`;
        appendMessage('assistant', data.response || 'No response received.', data.agent_type || 'general');
        currentSession = data.session;
        renderSessionState(data.session);
        updateProductsGrid(data.session ? data.session.products_found || [] : []);
        renderActionLog(data.session ? data.session.actions || [] : []);
        if (currentUser) {
            await Promise.all([loadTasks(), loadDashboard(), loadAudit()]);
        }
    } catch (error) {
        hideTyping();
        appendMessage('assistant', 'The assistant hit a temporary local error. Keep going and we will tighten that path next.', 'system');
    }
}

function sendQuick(prompt) {
    document.getElementById('msgInput').value = prompt;
    sendMessage();
}

async function registerAccount() {
    const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
            full_name: document.getElementById('authName').value.trim(),
            email: document.getElementById('authEmail').value.trim(),
            password: document.getElementById('authPassword').value
        })
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Registration failed');
        return;
    }
    await loadSessionState();
}

async function loginAccount() {
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
            email: document.getElementById('authEmail').value.trim(),
            password: document.getElementById('authPassword').value
        })
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Login failed');
        return;
    }
    await loadSessionState();
}

async function logoutAccount() {
    await fetch('/api/auth/logout', {method:'POST'});
    currentUser = null;
    currentWorkspace = null;
    currentTasks = [];
    currentDashboard = null;
    await loadSessionState();
}

async function createWorkspaceLocal() {
    if (!currentUser) {
        alert('Create or log into an account first.');
        return;
    }
    const name = prompt('Workspace name');
    if (!name) return;
    const res = await fetch('/api/workspaces', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name})
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Workspace creation failed');
        return;
    }
    await loadSessionState();
}

async function setBudget() {
    const budget = parseInt(document.getElementById('budgetInput').value, 10);
    if (!budget) return;
    const activeMode = document.querySelector('.mode-btn.active')?.id?.replace('btn-', '') || 'confirm';
    const res = await fetch('/set-budget', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({budget, approval_level: activeMode})
    });
    const data = await res.json();
    currentSession = data.session;
    renderSessionState(data.session);
    if (currentUser) {
        await loadDashboard();
    }
}

async function setApproval(level) {
    document.querySelectorAll('.mode-btn').forEach(button => button.classList.remove('active'));
    document.getElementById(`btn-${level}`).classList.add('active');
    const budget = currentSession?.budget || 0;
    const res = await fetch('/set-budget', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({budget, approval_level: level})
    });
    const data = await res.json();
    currentSession = data.session;
    renderSessionState(data.session);
}

async function quickTask(title, taskType, ownerAgent) {
    if (!currentUser) {
        alert('Sign in first so tasks can be saved to a workspace.');
        return;
    }
    const res = await fetch('/api/workspace/current/tasks', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({title, task_type: taskType, owner_agent: ownerAgent})
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Task creation failed');
        return;
    }
    await Promise.all([loadTasks(), loadDashboard(), loadAudit()]);
}

async function updateTaskStatus(taskId, status) {
    const res = await fetch(`/api/workspace/current/tasks/${taskId}`, {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({status})
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Task update failed');
        return;
    }
    await Promise.all([loadTasks(), loadDashboard(), loadAudit()]);
}

async function loadTasks() {
    const res = await fetch('/api/workspace/current/tasks');
    if (!res.ok) {
        renderTaskBoard([]);
        return;
    }
    const data = await res.json();
    currentTasks = data.tasks || [];
    renderTaskBoard(currentTasks);
}

function renderTaskBoard(tasks) {
    const queued = tasks.filter(task => task.status === 'queued');
    const inProgress = tasks.filter(task => task.status === 'in_progress');
    const completed = tasks.filter(task => task.status === 'completed');

    renderTaskColumn('taskQueued', queued, [
        {label:'Start', next:'in_progress'}
    ]);
    renderTaskColumn('taskInProgress', inProgress, [
        {label:'Done', next:'completed'}
    ]);
    renderTaskColumn('taskCompleted', completed, []);

    document.getElementById('tasksCount').textContent = tasks.length;
    document.getElementById('queueSummary').innerHTML = tasks.length
        ? tasks.slice(0, 3).map(task => `
            <div class="queue-card">
                <h4>${escapeHtml(task.title)}</h4>
                <p>${capitalize(task.owner_agent)} agent • ${task.status.replace('_', ' ')}</p>
            </div>
        `).join('')
        : '<div class="empty-state">Sign in and launch a workflow to build a queue.</div>';
}

function renderTaskColumn(elementId, tasks, actions) {
    const target = document.getElementById(elementId);
    if (!tasks.length) {
        target.innerHTML = '<div class="empty-state">No tasks in this lane.</div>';
        return;
    }
    target.innerHTML = tasks.map(task => `
        <div class="task-card">
            <div class="task-title">${escapeHtml(task.title)}</div>
            <div class="task-meta">${capitalize(task.owner_agent)} agent • ${task.task_type}</div>
            <div class="task-actions">
                ${actions.map(action => `<button onclick="updateTaskStatus('${task.id}', '${action.next}')">${action.label}</button>`).join('')}
            </div>
        </div>
    `).join('');
}

async function loadDashboard() {
    const res = await fetch('/api/workspace/current/dashboard');
    if (!res.ok) {
        renderDashboardSummary(null);
        return;
    }
    const data = await res.json();
    currentDashboard = data.summary;
    renderDashboardSummary(currentDashboard);
}

function renderDashboardSummary(summary) {
    const target = document.getElementById('dashboardSummary');
    if (!summary) {
        target.innerHTML = '<div class="empty-state">Sign in and work inside a saved workspace to unlock business-level analytics.</div>';
        document.getElementById('usageCount').textContent = '0';
        initCharts();
        return;
    }

    document.getElementById('usageCount').textContent = Object.values(summary.usage_by_kind || {}).reduce((total, value) => total + value, 0);
    target.innerHTML = `
        <div class="summary-card">
            <span class="metric-label">Budget</span>
            <strong>${formatCurrency(summary.budget)}</strong>
        </div>
        <div class="summary-card">
            <span class="metric-label">Spent</span>
            <strong>${formatCurrency(summary.spent)}</strong>
        </div>
        <div class="summary-card">
            <span class="metric-label">Audit Events</span>
            <strong>${summary.audit_event_count}</strong>
        </div>
        <div class="summary-card">
            <span class="metric-label">Usage Mix</span>
            <strong>${Object.keys(summary.usage_by_kind || {}).length}</strong>
        </div>
    `;
    initCharts(summary);
}

async function loadAudit() {
    const res = await fetch('/api/workspace/current/audit');
    if (!res.ok) {
        renderAudit([]);
        return;
    }
    const data = await res.json();
    renderAudit(data.events || []);
}

function renderAudit(events) {
    const target = document.getElementById('auditList');
    if (!events.length) {
        target.innerHTML = '<div class="empty-state">No workspace audit events yet.</div>';
        return;
    }
    target.innerHTML = events.map(event => `
        <div class="timeline-card">
            <h4>${escapeHtml(event.event_type)}</h4>
            <p>${escapeHtml(event.actor)} • ${formatTime(event.created_at)}</p>
        </div>
    `).join('');
}

function renderActionLog(actions) {
    const target = document.getElementById('actionLog');
    if (!actions || !actions.length) {
        target.innerHTML = '<div class="empty-state">No actions recorded yet.</div>';
        return;
    }
    target.innerHTML = actions.slice().reverse().map(action => `
        <div class="timeline-card">
            <h4>${escapeHtml(action.action || action.details || 'Action')}</h4>
            <p>${formatTime(action.time)}</p>
        </div>
    `).join('');
}

function updateProductsGrid(products) {
    const target = document.getElementById('productsGrid');
    if (!products || !products.length) {
        target.innerHTML = '<div class="empty-state">No product radar yet. Run a market scan.</div>';
        return;
    }
    target.innerHTML = products.map(product => `
        <button class="product-tile" onclick="sendQuick('Tell me more about ${escapeHtml(product)} for dropshipping')">
            <span class="product-name">${escapeHtml(product)}</span>
            <span class="product-meta">Open a deeper brief</span>
        </button>
    `).join('');
}

function renderGuestWorkspace() {
    renderTaskBoard([]);
    renderDashboardSummary(null);
    renderAudit([]);
    document.getElementById('historyList').innerHTML = renderConversationMemory(currentSession?.conversation || []);
}

function renderConversationMemory(messages) {
    if (!messages || !messages.length) {
        return '<div class="empty-state">No saved context yet.</div>';
    }
    return messages.slice().reverse().map(message => `
        <div class="timeline-card">
            <h4>${message.role === 'user' ? 'You' : 'Assistant'}</h4>
            <p>${escapeHtml((message.content || '').slice(0, 140))}</p>
        </div>
    `).join('');
}

async function loadHistory() {
    document.getElementById('historyList').innerHTML = renderConversationMemory(currentSession?.conversation || []);
}

function initCharts(summary) {
    const marginData = [68.7, 49.9, 33.2, 16.5];
    const budget = summary?.budget || currentSession?.budget || 100;
    const spent = summary?.spent || currentSession?.spent || 0;
    const remaining = Math.max(budget - spent, 0);

    if (profitChart) profitChart.destroy();
    if (budgetChart) budgetChart.destroy();

    const profitCtx = document.getElementById('profitChart');
    const budgetCtx = document.getElementById('budgetChart');
    if (!profitCtx || !budgetCtx) return;

    profitChart = new Chart(profitCtx, {
        type: 'line',
        data: {
            labels: ['Impulse', 'Problem Solver', 'Seasonal', 'Premium'],
            datasets: [{
                label: 'Expected margin %',
                data: marginData,
                borderColor: '#7f8cff',
                backgroundColor: 'rgba(127,140,255,.18)',
                fill: true,
                tension: .35
            }]
        },
        options: chartOptions()
    });

    budgetChart = new Chart(budgetCtx, {
        type: 'doughnut',
        data: {
            labels: ['Available', 'Spent'],
            datasets: [{
                data: [remaining || 0, spent || 0],
                backgroundColor: ['rgba(81,208,255,.7)', 'rgba(255,109,138,.7)'],
                borderColor: ['#51d0ff', '#ff6d8a'],
                borderWidth: 1
            }]
        },
        options: chartOptions(true)
    });
}

function chartOptions(isDoughnut = false) {
    return {
        responsive: true,
        plugins: {
            legend: {
                labels: {
                    color: '#96a1c2'
                }
            }
        },
        scales: isDoughnut ? {} : {
            x: {
                ticks: {color: '#96a1c2'},
                grid: {color: 'rgba(255,255,255,.06)'}
            },
            y: {
                ticks: {color: '#96a1c2'},
                grid: {color: 'rgba(255,255,255,.06)'}
            }
        }
    };
}

function capitalize(value) {
    if (!value) return '';
    return value.charAt(0).toUpperCase() + value.slice(1);
}
