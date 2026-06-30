import os
from dotenv import load_dotenv
load_dotenv()

from functools import wraps

from flask import Flask, request, jsonify, session, Response, render_template
from flask_cors import CORS
from agent import get_agent_response, get_session_data, set_budget, send_telegram
from database import db_manager
from platform_store import platform_store
import json
import uuid
import logging

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dropship-ai-secret-2024")   # needed for session tracking
CORS(app)
logging.basicConfig(level=logging.INFO)


def ensure_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    return platform_store.get_user(user_id)


def get_current_workspace():
    workspace_id = session.get('workspace_id')
    if not workspace_id:
        return None
    return platform_store.get_workspace(workspace_id)


def require_auth(route):
    @wraps(route)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required'}), 401
        return route(*args, **kwargs)

    return wrapper


def hydrate_session_from_workspace():
    workspace = get_current_workspace()
    if not workspace:
        return None

    snapshot = platform_store.get_latest_workspace_snapshot(workspace['id'])
    session_state = get_session_data(workspace['id'])
    session_state['session_id'] = workspace['id']

    if snapshot and snapshot.get('session_state'):
        session_state.update(snapshot['session_state'])

    settings = workspace.get('settings', {})
    session_state['budget'] = workspace.get('monthly_budget', session_state.get('budget', 0))
    session_state['approval_level'] = settings.get('approval_level', session_state.get('approval_level', 'confirm'))
    return session_state


def persist_workspace_session(session_state, event_type=None, payload=None):
    workspace = get_current_workspace()
    if not workspace:
        return

    settings = dict(workspace.get('settings', {}))
    settings['approval_level'] = session_state.get('approval_level', settings.get('approval_level', 'confirm'))
    platform_store.update_workspace(
        workspace['id'],
        {
            'monthly_budget': session_state.get('budget', workspace.get('monthly_budget', 0)),
            'settings': settings,
        },
    )
    platform_store.save_workspace_snapshot(workspace['id'], session_state)
    if event_type:
        platform_store.append_audit_event(
            workspace['id'],
            actor='user',
            event_type=event_type,
            payload=payload or {},
        )


def serialize_session_state(session_id):
    session_state = get_session_data(session_id)
    return {
        'session_id': session_state.get('session_id'),
        'budget': session_state.get('budget', 0),
        'spent': session_state.get('spent', 0),
        'approval_level': session_state.get('approval_level', 'confirm'),
        'actions': session_state.get('actions', [])[-20:],
        'products_found': session_state.get('products_found', [])[:8],
        'conversation': session_state.get('conversation', [])[-10:],
    }

HTML_PAGE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DropShip AI — Multi-Agent Platform</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Segoe UI',sans-serif;background:#0a0a16;color:#fff;height:100vh;display:flex;flex-direction:column}
        .header{background:linear-gradient(135deg,#1a1a3e 0%,#0d1b4b 100%);padding:14px 24px;display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2a5a}
        .logo{font-size:20px;font-weight:700;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .subtitle{font-size:12px;color:#8888aa;margin-top:2px}
        .agent-badge{background:#1e1e4a;border:1px solid #3a3a7a;border-radius:20px;padding:4px 12px;font-size:11px;color:#8888ff;margin-left:auto}
        .status-dot{width:8px;height:8px;background:#00ff88;border-radius:50%;animation:pulse 2s infinite;margin-left:8px}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}
        .main{display:flex;flex:1;overflow:hidden}
        .sidebar{width:260px;background:#0f0f2a;border-right:1px solid #1a1a3a;display:flex;flex-direction:column;padding:16px;gap:12px;overflow-y:auto}
        .sidebar-title{font-size:11px;color:#5555aa;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
        .budget-card{background:#1a1a3a;border-radius:10px;padding:14px;border:1px solid #2a2a5a}
        .budget-num{font-size:22px;font-weight:700;color:#667eea}
        .budget-label{font-size:11px;color:#5555aa;margin-top:2px}
        .budget-bar{height:6px;background:#2a2a5a;border-radius:3px;margin-top:10px;overflow:hidden}
        .budget-fill{height:100%;background:linear-gradient(90deg,#667eea,#764ba2);border-radius:3px;transition:width 0.5s}
        .stat-row{display:flex;gap:8px}
        .stat-box{flex:1;background:#1a1a3a;border-radius:8px;padding:10px;border:1px solid #2a2a5a;text-align:center}
        .stat-num{font-size:18px;font-weight:700;color:#00ff88}
        .stat-label{font-size:10px;color:#5555aa;margin-top:2px}
        .approval-section{background:#1a1a3a;border-radius:10px;padding:12px;border:1px solid #2a2a5a}
        .approval-btn{width:100%;padding:8px;border-radius:6px;border:1px solid #3a3a5a;background:#0f0f2a;color:#8888aa;font-size:12px;cursor:pointer;margin-top:6px;transition:all 0.2s}
        .approval-btn.active{background:#667eea;border-color:#667eea;color:#fff}
        .approval-btn:hover{border-color:#667eea;color:#fff}
        .quick-section{display:flex;flex-direction:column;gap:6px}
        .quick-btn{background:#1a1a3a;border:1px solid #2a2a5a;border-radius:8px;padding:9px 12px;font-size:12px;color:#8888cc;cursor:pointer;text-align:left;transition:all 0.2s}
        .quick-btn:hover{background:#2a2a5a;color:#fff;border-color:#667eea}
        .agent-indicator{font-size:10px;padding:2px 8px;border-radius:10px;margin-left:8px}
        .agent-trend{background:#0f2a1a;color:#00ff88;border:1px solid #00ff8844}
        .agent-supplier{background:#1a1a0f;color:#ffcc00;border:1px solid #ffcc0044}
        .agent-finance{background:#0f1a2a;color:#4488ff;border:1px solid #4488ff44}
        .agent-general{background:#2a0f2a;color:#cc88ff;border:1px solid #cc88ff44}
        .chat-area{flex:1;display:flex;flex-direction:column;overflow:hidden}
        .tabs{display:flex;gap:0;border-bottom:1px solid #1a1a3a;background:#0a0a16}
        .tab{padding:10px 20px;font-size:13px;cursor:pointer;color:#5555aa;border-bottom:2px solid transparent;transition:all 0.2s}
        .tab.active{color:#667eea;border-bottom-color:#667eea}
        .tab-content{flex:1;overflow:hidden;display:none}
        .tab-content.active{display:flex;flex-direction:column}
        .chat-container{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:12px}
        .message{max-width:78%;padding:12px 16px;border-radius:14px;line-height:1.6;font-size:14px}
        .user-msg{background:linear-gradient(135deg,#667eea,#764ba2);margin-left:auto;border-radius:14px 14px 4px 14px}
        .agent-msg{background:#1a1a3a;border:1px solid #2a2a5a;border-radius:14px 14px 14px 4px}
        .agent-msg pre{white-space:pre-wrap;font-family:inherit}
        .msg-header{display:flex;align-items:center;margin-bottom:4px;font-size:11px;color:#5555aa}
        .typing{display:flex;gap:4px;padding:12px 16px;background:#1a1a3a;border-radius:14px;width:fit-content;border:1px solid #2a2a5a}
        .dot{width:7px;height:7px;background:#667eea;border-radius:50%;animation:bounce 1.4s infinite}
        .dot:nth-child(2){animation-delay:.2s}
        .dot:nth-child(3){animation-delay:.4s}
        @keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-8px)}}
        .input-row{padding:16px;background:#0f0f2a;border-top:1px solid #1a1a3a;display:flex;gap:10px}
        .input-row input{flex:1;background:#1a1a3a;border:1px solid #2a2a5a;border-radius:22px;padding:11px 18px;color:#fff;font-size:14px;outline:none;transition:border-color 0.2s}
        .input-row input:focus{border-color:#667eea}
        .input-row button{background:linear-gradient(135deg,#667eea,#764ba2);border:none;border-radius:22px;padding:11px 22px;color:#fff;font-size:14px;cursor:pointer;font-weight:600}
        .dashboard-area{flex:1;overflow-y:auto;padding:20px;display:grid;grid-template-columns:1fr 1fr;gap:16px}
        .chart-card{background:#1a1a3a;border-radius:12px;padding:16px;border:1px solid #2a2a5a}
        .chart-title{font-size:13px;font-weight:600;color:#8888cc;margin-bottom:12px}
        .products-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-top:8px}
        .product-chip{background:#0f0f2a;border:1px solid #2a2a5a;border-radius:8px;padding:8px 10px;font-size:12px;color:#8888cc;text-align:center;cursor:pointer;transition:all 0.2s}
        .product-chip:hover{border-color:#667eea;color:#fff;background:#1a1a3a}
        .action-log{display:flex;flex-direction:column;gap:6px;margin-top:8px}
        .action-item{background:#0f0f2a;border-radius:6px;padding:8px 10px;font-size:11px;color:#5555aa;border-left:2px solid #667eea}
        .welcome-msg{text-align:center;padding:40px 20px;color:#5555aa}
        .welcome-msg h2{font-size:18px;color:#8888cc;margin-bottom:8px}
        .budget-input{display:flex;gap:6px;margin-top:8px}
        .budget-input input{flex:1;background:#0f0f2a;border:1px solid #2a2a5a;border-radius:6px;padding:6px 10px;color:#fff;font-size:12px;outline:none}
        .budget-input button{background:#667eea;border:none;border-radius:6px;padding:6px 12px;color:#fff;font-size:12px;cursor:pointer}
        .db-badge{font-size:10px;padding:2px 8px;border-radius:10px;margin-left:8px;background:#0f2a1a;color:#00ff88;border:1px solid #00ff8844}
        .auth-card{background:#131334;border:1px solid #2a2a5a;border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px}
        .auth-status{font-size:12px;color:#b9b9e8}
        .auth-input{width:100%;background:#0f0f2a;border:1px solid #2a2a5a;border-radius:6px;padding:7px 10px;color:#fff;font-size:12px;outline:none}
        .auth-actions{display:flex;gap:6px}
        .auth-actions button{flex:1;background:#1a1a3a;border:1px solid #2a2a5a;border-radius:6px;padding:7px 10px;color:#fff;font-size:12px;cursor:pointer}
        .workspace-card{background:#15153a;border:1px solid #2a2a5a;border-radius:10px;padding:12px}
        .workspace-meta{font-size:11px;color:#8888cc;line-height:1.5}
    </style>
</head>
<body>
<div class="header">
    <div>
        <div class="logo">DropShip AI Agent</div>
        <div class="subtitle">Multi-Agent Platform — Gemini 2.5 + MCP + ADK + AlloyDB + Cloud Run</div>
    </div>
    <div class="agent-badge" id="currentAgent">General Agent</div>
    <div class="db-badge" id="dbBadge">DB ●</div>
    <div class="status-dot"></div>
</div>
<div class="main">
    <div class="sidebar">
        <div>
            <div class="sidebar-title">Account</div>
            <div class="auth-card">
                <div class="auth-status" id="authStatus">Local guest mode</div>
                <input class="auth-input" id="authName" placeholder="Full name" />
                <input class="auth-input" id="authEmail" placeholder="Email" />
                <input class="auth-input" id="authPassword" type="password" placeholder="Password" />
                <div class="auth-actions">
                    <button onclick="registerAccount()">Register</button>
                    <button onclick="loginAccount()">Login</button>
                </div>
                <div class="auth-actions">
                    <button onclick="logoutAccount()">Logout</button>
                    <button onclick="createWorkspaceLocal()">New Workspace</button>
                </div>
            </div>
        </div>
        <div>
            <div class="sidebar-title">Workspace</div>
            <div class="workspace-card">
                <div style="font-size:15px;font-weight:700;color:#fff" id="workspaceName">Session Workspace</div>
                <div class="workspace-meta" id="workspaceMeta">Sign in to save products, tasks, audit logs, and business history locally.</div>
            </div>
        </div>
        <div>
            <div class="sidebar-title">Budget Tracker</div>
            <div class="budget-card">
                <div class="budget-num" id="budgetNum">₹0</div>
                <div class="budget-label">Total Budget</div>
                <div class="budget-bar"><div class="budget-fill" id="budgetFill" style="width:0%"></div></div>
                <div style="font-size:11px;color:#5555aa;margin-top:6px">Spent: <span id="spentNum">₹0</span></div>
            </div>
            <div class="budget-input">
                <input type="number" id="budgetInput" placeholder="Set budget ₹" />
                <button onclick="setBudget()">Set</button>
            </div>
        </div>
        <div class="stat-row">
            <div class="stat-box"><div class="stat-num" id="productsFound">0</div><div class="stat-label">Products Found</div></div>
            <div class="stat-box"><div class="stat-num" id="actionsCount">0</div><div class="stat-label">Actions</div></div>
        </div>
        <div>
            <div class="sidebar-title">Approval Level</div>
            <div class="approval-section">
                <div style="font-size:11px;color:#5555aa;margin-bottom:6px">Agent asks before acting</div>
                <button class="approval-btn active" id="btn-confirm" onclick="setApproval('confirm')">Confirm each action</button>
                <button class="approval-btn" id="btn-view" onclick="setApproval('view')">View only — no actions</button>
                <button class="approval-btn" id="btn-auto" onclick="setApproval('auto')">Full auto within budget</button>
            </div>
        </div>
        <div>
            <div class="sidebar-title">Quick Actions</div>
            <div class="quick-section">
                <button class="quick-btn" onclick="sendQuick('What are the trending products in Delhi right now?')">Delhi trends</button>
                <button class="quick-btn" onclick="sendQuick('Show trending products in USA')">USA trends</button>
                <button class="quick-btn" onclick="sendQuick('Calculate profit: cost ₹200, selling ₹599, 50 units')">Profit calculator</button>
                <button class="quick-btn" onclick="sendQuick('Find best suppliers for bluetooth earbuds')">Find suppliers</button>
                <button class="quick-btn" onclick="sendQuick('Give me a complete beginner dropshipping roadmap')">Beginner roadmap</button>
                <button class="quick-btn" onclick="sendQuick('What products are trending in Mumbai?')">Mumbai trends</button>
                <button class="quick-btn" onclick="sendQuick('Compare AliExpress vs CJ Dropshipping vs Zendrop')">Compare suppliers</button>
                <button class="quick-btn" onclick="sendQuick('Research and analyze air purifier product in depth')">Research product</button>
            </div>
        </div>
    </div>
    <div class="chat-area">
        <div class="tabs">
            <div class="tab active" onclick="switchTab('chat')">Chat</div>
            <div class="tab" onclick="switchTab('dashboard')">Analytics</div>
            <div class="tab" onclick="switchTab('actions')">Action Log</div>
            <div class="tab" onclick="switchTab('history')">History</div>
        </div>
        <div class="tab-content active" id="tab-chat">
            <div class="chat-container" id="chatContainer">
                <div class="welcome-msg">
                    <h2>DropShip AI Agent Ready</h2>
                    <p>Ask me about trending products, suppliers, profits, or strategy.</p>
                </div>
            </div>
            <div class="input-row">
                <input type="text" id="msgInput" placeholder="Ask anything about dropshipping..." onkeydown="if(event.key==='Enter')sendMessage()" />
                <button onclick="sendMessage()">Send</button>
            </div>
        </div>
        <div class="tab-content" id="tab-dashboard">
            <div class="dashboard-area">
                <div class="chart-card">
                    <div class="chart-title">Profit Margin Analysis</div>
                    <canvas id="profitChart"></canvas>
                </div>
                <div class="chart-card">
                    <div class="chart-title">Budget Allocation</div>
                    <canvas id="budgetChart"></canvas>
                </div>
                <div class="chart-card" style="grid-column:1/-1">
                    <div class="chart-title">Trending Products This Session</div>
                    <div class="products-grid" id="productsGrid">
                        <div style="color:#5555aa;font-size:12px">No products found yet — ask about trending products!</div>
                    </div>
                </div>
            </div>
        </div>
        <div class="tab-content" id="tab-actions">
            <div style="padding:20px;flex:1;overflow-y:auto">
                <div class="chart-title" style="margin-bottom:12px">Agent Action Log</div>
                <div class="action-log" id="actionLog">
                    <div style="color:#5555aa;font-size:12px">No actions yet.</div>
                </div>
            </div>
        </div>
        <div class="tab-content" id="tab-history">
            <div style="padding:20px;flex:1;overflow-y:auto">
                <div class="chart-title" style="margin-bottom:12px">Conversation History (AlloyDB)</div>
                <div id="historyList" style="display:flex;flex-direction:column;gap:8px">
                    <div style="color:#5555aa;font-size:12px">Loading history...</div>
                </div>
            </div>
        </div>
    </div>
</div>
<script>
let profitChart, budgetChart;
let currentSession = null;
let currentUser = null;
let currentWorkspace = null;
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    document.getElementById('dbBadge').textContent = 'Loading';
    loadSessionState();
});

function switchTab(name) {
    document.querySelectorAll('.tab').forEach((t,i) => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    const tabs = ['chat','dashboard','actions','history'];
    const idx = tabs.indexOf(name);
    document.querySelectorAll('.tab')[idx].classList.add('active');
    document.getElementById('tab-' + name).classList.add('active');
    if (name === 'dashboard') initCharts();
    if (name === 'history') loadHistory();
}

function setApproval(level) {
    ['confirm','view','auto'].forEach(l => document.getElementById('btn-'+l).classList.remove('active'));
    document.getElementById('btn-'+level).classList.add('active');
    fetch('/set-budget', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({budget: currentSession ? currentSession.budget : 0, approval_level: level})
    }).then(r => r.json()).then(d => {
        updateSidebar(d.session);
        renderActionLog(d.session ? d.session.actions : []);
    });
}

function setBudget() {
    const val = parseInt(document.getElementById('budgetInput').value);
    if (!val) return;
    const level = document.querySelector('.approval-btn.active').textContent.includes('Confirm') ? 'confirm' :
                  document.querySelector('.approval-btn.active').textContent.includes('View') ? 'view' : 'auto';
    fetch('/set-budget', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({budget: val, approval_level: level})
    }).then(r => r.json()).then(d => updateSidebar(d.session));
}

function sendQuick(msg) {
    document.getElementById('msgInput').value = msg;
    sendMessage();
}

async function loadSessionState() {
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/session', { signal: controller.signal });
        clearTimeout(timer);
        const data = await res.json();
        updateSidebar(data.session);
        renderAuthState(data.user, data.workspace);
        if (data.session && data.session.products_found && data.session.products_found.length > 0) {
            updateProductsGrid(data.session.products_found);
        }
        renderActionLog(data.session ? data.session.actions : []);
        const badge = document.getElementById('dbBadge');
        badge.style.color = data.db_connected ? '#00ff88' : '#ffcc66';
        badge.textContent = data.db_connected ? 'DB connected' : 'DB optional';
    } catch (e) {
        const badge = document.getElementById('dbBadge');
        badge.style.color = '#ffcc66';
        badge.textContent = 'Offline-ready';
    }
}

function renderAuthState(user, workspace) {
    currentUser = user || null;
    currentWorkspace = workspace || null;
    document.getElementById('authStatus').textContent = user
        ? `Signed in as ${user.full_name}`
        : 'Local guest mode';
    document.getElementById('workspaceName').textContent = workspace ? workspace.name : 'Session Workspace';
    document.getElementById('workspaceMeta').textContent = workspace
        ? `${workspace.country} • ${workspace.niche || 'General niche'} • Stage: ${workspace.store_stage}`
        : 'Sign in to save products, tasks, audit logs, and business history locally.';
}

async function registerAccount() {
    const payload = {
        full_name: document.getElementById('authName').value.trim(),
        email: document.getElementById('authEmail').value.trim(),
        password: document.getElementById('authPassword').value
    };
    const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Registration failed');
        return;
    }
    renderAuthState(data.user, data.workspace);
    await loadSessionState();
}

async function loginAccount() {
    const payload = {
        email: document.getElementById('authEmail').value.trim(),
        password: document.getElementById('authPassword').value
    };
    const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
        alert(data.error || 'Login failed');
        return;
    }
    renderAuthState(data.user, data.workspace);
    await loadSessionState();
}

async function logoutAccount() {
    await fetch('/api/auth/logout', {method:'POST'});
    renderAuthState(null, null);
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
    renderAuthState(currentUser, data.workspace);
    await loadSessionState();
}

async function sendMessage() {
    const input = document.getElementById('msgInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    switchTab('chat');
    const chat = document.getElementById('chatContainer');
    const welcome = chat.querySelector('.welcome-msg');
    if (welcome) welcome.remove();
    chat.innerHTML += `<div class="message user-msg">${msg}</div>`;
    chat.innerHTML += `<div class="typing" id="typing"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>`;
    chat.scrollTop = chat.scrollHeight;
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 45000);
        const res = await fetch('/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: msg}),
            signal: controller.signal
        });
        clearTimeout(timer);
        const data = await res.json();
        document.getElementById('typing').remove();
        const agentClass = 'agent-' + (data.agent_type || 'general');
        const agentLabel = (data.agent_type || 'general').charAt(0).toUpperCase() + (data.agent_type || 'general').slice(1) + ' Agent';
        document.getElementById('currentAgent').textContent = agentLabel;
        chat.innerHTML += `<div class="message agent-msg">
            <div class="msg-header"><span class="agent-indicator ${agentClass}">${agentLabel}</span></div>
            <pre>${data.response}</pre>
        </div>`;
        updateSidebar(data.session);
        if (data.session && data.session.products_found && data.session.products_found.length > 0) {
            updateProductsGrid(data.session.products_found);
        }
        renderActionLog(data.session ? data.session.actions : []);
        addAction('Query processed by ' + agentLabel);
    } catch(e) {
        document.getElementById('typing')?.remove();
        chat.innerHTML += `<div class="message agent-msg">The assistant took too long or hit a temporary error. Please try again.</div>`;
    }
    chat.scrollTop = chat.scrollHeight;
}

function updateSidebar(session) {
    if (!session) return;
    currentSession = session;
    document.getElementById('budgetNum').textContent = '₹' + (session.budget || 0).toLocaleString();
    document.getElementById('spentNum').textContent = '₹' + (session.spent || 0).toLocaleString();
    document.getElementById('productsFound').textContent = session.products_found ? session.products_found.length : 0;
    document.getElementById('actionsCount').textContent = session.actions ? session.actions.length : 0;
    const pct = session.budget > 0 ? Math.min((session.spent / session.budget) * 100, 100) : 0;
    document.getElementById('budgetFill').style.width = pct + '%';
}

function updateProductsGrid(products) {
    const grid = document.getElementById('productsGrid');
    grid.innerHTML = products.map(p => `<div class="product-chip" onclick="sendQuick('Tell me more about ${p} for dropshipping')">${p}</div>`).join('');
}

function renderActionLog(actions) {
    const log = document.getElementById('actionLog');
    if (!actions || actions.length === 0) {
        log.innerHTML = '<div style="color:#5555aa;font-size:12px">No actions yet.</div>';
        return;
    }
    log.innerHTML = actions.slice().reverse().map(action => {
        const label = action.action || action.details || 'Action';
        const time = action.time ? new Date(action.time).toLocaleTimeString() : 'Now';
        return `<div class="action-item">[${time}] ${label}</div>`;
    }).join('');
}

function addAction(text) {
    const log = document.getElementById('actionLog');
    const empty = log.querySelector('div[style]');
    if (empty) empty.remove();
    const time = new Date().toLocaleTimeString();
    log.innerHTML = `<div class="action-item">[${time}] ${text}</div>` + log.innerHTML;
}

async function checkDbHealth() {
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/db/health', { signal: controller.signal });
        clearTimeout(timer);
        const data = await res.json();
        const badge = document.getElementById('dbBadge');
        if (data.status === 'healthy') {
            badge.style.color = '#00ff88';
            badge.textContent = 'DB ● ' + data.conversations + ' convos';
        } else {
            badge.style.color = '#ff4444';
            badge.textContent = 'DB ✕';
        }
    } catch(e) {
        document.getElementById('dbBadge').style.color = '#ff4444';
    }
}

async function loadHistory() {
    try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 4000);
        const res = await fetch('/api/history', { signal: controller.signal });
        clearTimeout(timer);
        const data = await res.json();
        const list = document.getElementById('historyList');
        if (!data.history || data.history.length === 0) {
            list.innerHTML = '<div style="color:#5555aa;font-size:12px">No history yet — start chatting!</div>';
            return;
        }
        list.innerHTML = data.history.map(h => `
            <div class="action-item" style="border-left-color:#764ba2">
                <div style="color:#8888cc;margin-bottom:4px">[${h.agent_type}] ${new Date(h.created_at).toLocaleString()}</div>
                <div style="color:#aaaacc">You: ${h.user_message.substring(0,80)}${h.user_message.length>80?'...':''}</div>
            </div>
        `).join('');
    } catch(e) {
        document.getElementById('historyList').innerHTML = '<div style="color:#5555aa;font-size:12px">History unavailable.</div>';
    }
}

function initCharts() {
    if (profitChart) profitChart.destroy();
    if (budgetChart) budgetChart.destroy();
    const pCtx = document.getElementById('profitChart').getContext('2d');
    profitChart = new Chart(pCtx, {
        type: 'bar',
        data: {
            labels: ['Cost ₹200', 'Cost ₹300', 'Cost ₹400', 'Cost ₹500'],
            datasets: [{
                label: 'Margin % at ₹599 selling',
                data: [66.6, 49.9, 33.2, 16.5],
                backgroundColor: ['#667eea88','#764ba288','#5a3f9088','#44299088'],
                borderColor: ['#667eea','#764ba2','#5a3f90','#442990'],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {labels: {color: '#8888cc', font: {size: 11}}}},
            scales: {
                x: {ticks: {color: '#5555aa'}, grid: {color: '#1a1a3a'}},
                y: {ticks: {color: '#5555aa'}, grid: {color: '#1a1a3a'}}
            }
        }
    });
    const bCtx = document.getElementById('budgetChart').getContext('2d');
    budgetChart = new Chart(bCtx, {
        type: 'doughnut',
        data: {
            labels: ['Inventory 60%', 'Marketing 30%', 'Reserve 10%'],
            datasets: [{
                data: [60, 30, 10],
                backgroundColor: ['#667eea88','#764ba288','#44299088'],
                borderColor: ['#667eea','#764ba2','#442990'],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {legend: {labels: {color: '#8888cc', font: {size: 11}}}}
        }
    });
}
</script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return ('', 204)

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    try:
        result = platform_store.register_user(
            email=data.get('email', ''),
            password=data.get('password', ''),
            full_name=data.get('full_name', ''),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    session['user_id'] = result['user']['id']
    session['workspace_id'] = result['workspace']['id']
    workspace_session = get_session_data(result['workspace']['id'])
    workspace_session['session_id'] = result['workspace']['id']
    persist_workspace_session(workspace_session, 'auth.registered', {'email': result['user']['email']})
    return jsonify({
        'user': result['user'],
        'workspace': result['workspace'],
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    user = platform_store.authenticate_user(
        email=data.get('email', ''),
        password=data.get('password', ''),
    )
    if not user:
        return jsonify({'error': 'Invalid email or password'}), 401

    workspaces = platform_store.list_workspaces(user['id'])
    workspace = workspaces[0] if workspaces else platform_store.create_workspace(user['id'], f"{user['full_name']}'s Workspace")
    session['user_id'] = user['id']
    session['workspace_id'] = workspace['id']
    hydrate_session_from_workspace()
    return jsonify({
        'user': user,
        'workspace': workspace,
        'workspaces': workspaces or [workspace],
    })

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('workspace_id', None)
    return jsonify({'success': True})

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = get_current_user()
    workspace = get_current_workspace()
    return jsonify({
        'authenticated': bool(user),
        'user': user,
        'workspace': workspace,
        'workspaces': platform_store.list_workspaces(user['id']) if user else [],
    })

@app.route('/api/workspaces', methods=['GET'])
@require_auth
def list_workspaces():
    user = get_current_user()
    return jsonify({'workspaces': platform_store.list_workspaces(user['id'])})

@app.route('/api/workspaces', methods=['POST'])
@require_auth
def create_workspace():
    user = get_current_user()
    data = request.json or {}
    workspace = platform_store.create_workspace(
        user_id=user['id'],
        name=data.get('name', 'New Workspace'),
        country=data.get('country', 'IN'),
        niche=data.get('niche', ''),
        monthly_budget=float(data.get('monthly_budget', 0) or 0),
    )
    session['workspace_id'] = workspace['id']
    hydrate_session_from_workspace()
    return jsonify({'workspace': workspace})

@app.route('/api/workspace/current', methods=['GET'])
@require_auth
def current_workspace():
    workspace = get_current_workspace()
    snapshot = platform_store.get_latest_workspace_snapshot(workspace['id']) if workspace else None
    return jsonify({
        'workspace': workspace,
        'snapshot': snapshot,
    })

@app.route('/api/workspace/current', methods=['PUT'])
@require_auth
def update_current_workspace():
    workspace = get_current_workspace()
    data = request.json or {}
    updated = platform_store.update_workspace(workspace['id'], data)
    hydrate_session_from_workspace()
    return jsonify({'workspace': updated})

@app.route('/api/workspace/current/tasks', methods=['GET'])
@require_auth
def workspace_tasks():
    workspace = get_current_workspace()
    return jsonify({'tasks': platform_store.list_tasks(workspace['id'])})

@app.route('/api/workspace/current/tasks', methods=['POST'])
@require_auth
def create_workspace_task():
    workspace = get_current_workspace()
    data = request.json or {}
    task = platform_store.create_task(
        workspace_id=workspace['id'],
        title=data.get('title', 'Untitled Task'),
        task_type=data.get('task_type', 'manual'),
        status=data.get('status', 'queued'),
        owner_agent=data.get('owner_agent', 'general'),
        details=data.get('details', {}),
    )
    return jsonify({'task': task})

@app.route('/api/workspace/current/tasks/<task_id>', methods=['PUT'])
@require_auth
def update_workspace_task(task_id):
    workspace = get_current_workspace()
    data = request.json or {}
    task = platform_store.update_task(workspace['id'], task_id, data)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({'task': task})

@app.route('/api/workspace/current/audit', methods=['GET'])
@require_auth
def workspace_audit():
    workspace = get_current_workspace()
    return jsonify({'events': platform_store.list_audit_events(workspace['id'])})

@app.route('/api/workspace/current/dashboard', methods=['GET'])
@require_auth
def workspace_dashboard():
    workspace = get_current_workspace()
    return jsonify({'summary': platform_store.get_dashboard_summary(workspace['id'])})

@app.route('/api/session', methods=['GET'])
def session_state():
    session_id = ensure_session_id()
    workspace_session = hydrate_session_from_workspace()
    return jsonify({
        'session': serialize_session_state(session.get('workspace_id') or session_id),
        'db_connected': db_manager.is_connected,
        'authenticated': bool(get_current_user()),
        'user': get_current_user(),
        'workspace': get_current_workspace(),
    })

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')
    if not message:
        return jsonify({'error': 'No message'}), 400

    # Get or create session ID for DB tracking
    session_id = session.get('workspace_id') or ensure_session_id()
    if session.get('workspace_id'):
        hydrate_session_from_workspace()

    try:
        response, agent_type = get_agent_response(message, session_id)
        if session.get('workspace_id'):
            platform_store.record_usage(session['workspace_id'], 'chat_request', 1, {'agent_type': agent_type})
            platform_store.append_audit_event(
                session['workspace_id'],
                actor='user',
                event_type='chat.completed',
                payload={'agent_type': agent_type, 'message': message[:200]},
            )
            persist_workspace_session(get_session_data(session_id))
        sess = serialize_session_state(session_id)
        return jsonify({
            'response': response,
            'agent_type': agent_type,
            'session': sess
        })
    except Exception as e:
        app.logger.exception("Chat request failed")
        return jsonify({
            'response': 'The assistant is temporarily unavailable. Please check deployment logs and try again.',
            'agent_type': 'general',
            'session': serialize_session_state(session_id),
            'error': str(e)
        }), 503

@app.route('/set-budget', methods=['POST'])
def budget():
    data = request.json
    session_id = session.get('workspace_id') or ensure_session_id()
    result = set_budget(data.get('budget', 0), data.get('approval_level', 'confirm'), session_id)
    if session.get('workspace_id'):
        platform_store.record_usage(session['workspace_id'], 'budget_update', 1, result)
        persist_workspace_session(
            get_session_data(session_id),
            'budget.updated',
            {'budget': result['budget'], 'approval_level': result['approval_level']},
        )
    return jsonify({'success': True, 'session': serialize_session_state(session_id)})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'version': '3.0', 'agents': ['trend', 'supplier', 'finance', 'general'], 'db': db_manager.is_connected})

# ── AlloyDB API endpoints ──────────────────────────────────────────────────────

@app.route('/api/db/health', methods=['GET'])
def db_health():
    return jsonify(db_manager.health_check())

@app.route('/api/history', methods=['GET'])
def get_history():
    session_id = session.get('workspace_id') or ensure_session_id()
    history = db_manager.get_conversation_history(session_id, limit=50)
    return jsonify({'history': history})

@app.route('/api/products', methods=['GET'])
def get_products():
    category = request.args.get('category')
    min_margin = request.args.get('min_margin', type=float)
    products = db_manager.get_products(category=category, min_margin=min_margin)
    return jsonify({'products': products})

@app.route('/api/products/save', methods=['POST'])
def save_product():
    data = request.json
    product_id = db_manager.save_product(data)
    return jsonify({'success': bool(product_id), 'id': product_id})

@app.route('/api/profile', methods=['GET'])
def get_profile():
    session_id = session.get('workspace_id') or ensure_session_id()
    profile = db_manager.get_or_create_profile(session_id)
    session_state = get_session_data(session_id)
    session_state['budget'] = profile.get('budget_total', session_state.get('budget', 0))
    session_state['spent'] = profile.get('budget_spent', session_state.get('spent', 0))
    session_state['approval_level'] = profile.get('approval_level', session_state.get('approval_level', 'confirm'))
    return jsonify(profile)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
