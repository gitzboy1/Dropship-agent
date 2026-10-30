# DropShip AI Agent — Multi-Agent Dropshipping Intelligence Platform

> An AI-powered dropshipping assistant that uses **Google Gemini 2.5 Flash**, a **multi-agent orchestrator**, **AlloyDB (PostgreSQL)** for persistent storage, **Telegram** for push notifications, and a full-featured **Flask** web dashboard — all deployable to **Google Cloud Run** with a single `cloudbuild` push.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Tech Stack & Why Each Was Chosen](#tech-stack--why-each-was-chosen)
3. [Architecture Diagram](#architecture-diagram)
4. [Project Structure](#project-structure)
5. [File-by-File Breakdown](#file-by-file-breakdown)
   - [app.py](#apppy--flask-web-server--api-gateway)
   - [agent.py](#agentpy--multi-agent-orchestrator--business-logic)
   - [database.py](#databasepy--alloydb-integration--orm-models)
   - [platform_store.py](#platform_storepy--local-json-workspace-store)
   - [browser_agent.py](#browser_agentpy--product-research--browser-automation)
   - [telegram_fix.py](#telegram_fixpy--telegram-notification-service)
   - [setup_db.py](#setup_dbpy--one-time-database-bootstrap)
   - [templates/index.html](#templatesindexhtml--frontend-html-shell)
   - [static/app.css](#staticappcss--frontend-styles)
   - [static/app.js](#staticappjs--frontend-javascript-logic)
   - [Configuration & DevOps Files](#configuration--devops-files)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [Multi-Agent System](#multi-agent-system)
8. [Database Schema](#database-schema)
9. [Environment Variables](#environment-variables)
10. [Getting Started](#getting-started)
11. [Deployment (Google Cloud Run)](#deployment-google-cloud-run)

---

## Project Overview

**DropShip AI Agent** is a full-stack web application that acts as an intelligent assistant for anyone running (or starting) a dropshipping business. It combines:

| Capability | How It Works |
|---|---|
| **Trend Discovery** | Pulls Google Trends data (or curated fallback lists) for India, USA, and UK markets |
| **Supplier Intelligence** | Maintains a structured supplier database (AliExpress, CJ Dropshipping, Zendrop, Spocket) |
| **Profit & Budget Analysis** | Real-time margin/ROI calculator and budget allocation engine |
| **AI Chat (Gemini 2.5 Flash)** | Four specialised sub-agents handle different query types via a single orchestrator |
| **Workspace Management** | Per-user workspaces with tasks, audit trails, snapshots, and usage tracking |
| **Telegram Notifications** | Push alerts for trends found, budget approvals, supplier matches, and errors |
| **Persistent Storage (AlloyDB)** | Conversations, products, user profiles, and budget transactions stored in PostgreSQL |
| **Vector Search (pgvector)** | Product embeddings for semantic similarity search |

---

## Tech Stack & Why Each Was Chosen

### Backend

| Technology | Version | Why It Was Chosen |
|---|---|---|
| **Python 3.11** | 3.11 | Primary language — rich AI/ML ecosystem, fast prototyping |
| **Flask** | 3.0.0 | Lightweight web framework — minimal boilerplate, easy to add routes, good for API-first apps |
| **Flask-CORS** | 4.0.0 | Enables Cross-Origin Resource Sharing — needed when the frontend runs on a different origin during development |
| **Gunicorn** | 21.2.0 | Production-grade WSGI server — replaces Flask's dev server for Cloud Run deployment |
| **google-genai** | 1.10.0 | Official Google Generative AI SDK — connects to **Gemini 2.5 Flash** for AI text generation |
| **SQLAlchemy** | 2.0.23 | ORM for PostgreSQL — provides a clean model layer over AlloyDB without raw SQL |
| **pg8000** | 1.30.3 | Pure-Python PostgreSQL driver — no C dependencies, works inside slim Docker images |
| **pgvector** | 0.2.4 | Enables vector similarity search on product embeddings inside AlloyDB |
| **google-cloud-alloydb-connector** | 1.0.0 | Secure IAM-based connector for AlloyDB (optional, for VPC-less access) |
| **pytrends** | 4.9.2 | Unofficial Google Trends API — fetches real-time trending product queries |
| **requests** | 2.31.0 | HTTP client — used for Telegram API calls and supplier scraping |
| **python-telegram-bot** | 21.0.1 | Telegram Bot API SDK (installed but the project uses raw `requests` for reliability) |
| **python-dotenv** | — | Loads `.env` file into `os.environ` at startup |
| **Werkzeug** | (Flask dep) | Provides `generate_password_hash` and `check_password_hash` for user auth |
| **browser-use** | — | AI-driven browser automation agent (optional — used for deep product research) |
| **langchain-google-genai** | — | LangChain integration for Gemini (used by `browser-use` agent) |
| **Playwright** | — | Headless browser engine for `browser-use` (optional dependency) |
| **BeautifulSoup4** | — | HTML parser (available for scraping, not actively used in current code) |
| **APScheduler** | 3.10.4 | Task scheduler (installed for future scheduled jobs) |

### Frontend

| Technology | Why It Was Chosen |
|---|---|
| **Vanilla HTML/CSS/JS** | Zero build step — served directly by Flask's `render_template` and static file serving |
| **Manrope + Space Grotesk** (Google Fonts) | Modern typography — premium feel with clear hierarchy |
| **Chart.js 4.4.0** (CDN) | Interactive charts for profit margins and budget allocation |
| **CSS Custom Properties + Glassmorphism** | Dark-mode-first design system with `backdrop-filter` blur and gradient accents |

### Infrastructure & DevOps

| Technology | Why It Was Chosen |
|---|---|
| **Docker** | Containerisation — ensures identical environments locally and in production |
| **Google Cloud Build** | CI/CD pipeline — builds the Docker image, pushes to Artifact Registry, and deploys to Cloud Run |
| **Google Cloud Run** | Serverless container hosting — scales to zero, pay-per-request, no infra management |
| **Google AlloyDB** | Fully managed PostgreSQL-compatible database with pgvector support for vector search |
| **Google Artifact Registry** | Private Docker image registry (replaces deprecated Container Registry) |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Browser (User)                              │
│   templates/index.html  +  static/app.css  +  static/app.js        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  HTTP (fetch API)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    app.py (Flask Server)                             │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐   │
│  │ Auth Routes  │  │ Chat Route   │  │ Workspace / Task Routes   │   │
│  │ /api/auth/*  │  │ /chat        │  │ /api/workspace/*          │   │
│  └──────┬──────┘  └──────┬───────┘  └────────────┬──────────────┘   │
│         │                │                       │                   │
│         ▼                ▼                       ▼                   │
│  platform_store.py    agent.py             platform_store.py         │
│  (JSON file store)   (Orchestrator)        (JSON file store)         │
└─────────────────────────┬───────────────────────────────────────────┘
                          │
            ┌─────────────┼─────────────────┐
            ▼             ▼                 ▼
    ┌──────────────┐  ┌──────────┐  ┌──────────────┐
    │ Gemini 2.5   │  │ database │  │ telegram_fix │
    │ Flash API    │  │ .py      │  │ .py          │
    │ (4 agents)   │  │ (AlloyDB)│  │ (Push alerts)│
    └──────────────┘  └──────────┘  └──────────────┘
                          │
                          ▼
                   ┌──────────────┐
                   │ AlloyDB /    │
                   │ PostgreSQL   │
                   │ + pgvector   │
                   └──────────────┘
```

---

## Project Structure

After cleanup the project contains these files:

```
dropship-agent/
│
├── app.py                    # Flask web server, all API routes, inline HTML (legacy)
├── agent.py                  # Multi-agent orchestrator, Gemini integration, business logic
├── database.py               # AlloyDB/PostgreSQL ORM models and database manager
├── platform_store.py         # Local JSON-based workspace, user, task, and audit store
├── browser_agent.py          # Product research via browser automation (supplier scraping)
├── telegram_fix.py           # Telegram notification service (non-blocking, thread-safe)
├── setup_db.py               # One-time script to bootstrap AlloyDB database and extensions
│
├── templates/
│   └── index.html            # Main frontend HTML (served by Flask's render_template)
│
├── static/
│   ├── app.css               # Full CSS design system (dark theme, glassmorphism, responsive)
│   └── app.js                # Frontend JavaScript (chat, auth, tasks, charts, state management)
│
├── data/
│   └── platform_store.json   # Auto-generated JSON file for local workspace persistence
│
├── requirements.txt          # Python dependencies
├── Dockerfile                # Docker container build instructions
├── cloudbuild_update.yaml    # Google Cloud Build CI/CD pipeline definition
├── env.yaml                  # Environment variables for Cloud Run deployment (SECRETS)
├── env.yaml.example          # Template for env.yaml (safe to commit)
├── .env                      # Local environment variables (SECRETS — gitignored)
├── .env.example              # Template for .env (safe to commit)
├── .gitignore                # Git ignore rules
├── .dockerignore             # Docker build ignore rules
└── README.md                 # This file
```

### Files That Were Removed During Cleanup

| File / Directory | Reason for Removal |
|---|---|
| `__pycache__/` (150 stale `.pyc` files) | Python bytecode cache — auto-generated, should never be committed |
| `package-lock.json` | Empty npm lock file — this is a Python project, not a Node.js project |
| `platform.db` + `platform.db-journal` (root) | SQLite databases generated at runtime — should not be committed |
| `data/plain.txt` | Test placeholder file containing only "ok" — no purpose |
| `data/platform.db` + `data/platform.db-journal` | Duplicate SQLite databases inside data/ — auto-generated |
| `.gcloud/` | Local Google Cloud SDK config directory — machine-specific, already gitignored |
| `env_setup.bat` | Contained hardcoded secrets — `.env` file serves the same purpose |
| `env_setup.bat.example` | Redundant — `.env.example` already provides the same template |

---

## File-by-File Breakdown

---

### `app.py` — Flask Web Server & API Gateway

**Lines:** 905 | **Size:** ~41 KB | **Role:** Central entry point — starts the web server, defines all HTTP routes, and connects the frontend to the backend services.

#### Key Sections

| Lines | What It Does | Why |
|---|---|---|
| **1–19** | **Imports & app init.** Loads `.env`, creates the Flask app, enables CORS, sets a secret key for session cookies, and configures logging. | Flask needs a `secret_key` for server-side session data. CORS is required because the frontend may be on a different origin during development. |
| **22–25** | **`ensure_session_id()`** — Generates a UUID-based session ID and stores it in Flask's server-side session. | Every user needs a unique session to track their state (budget, products, conversation) across multiple requests. |
| **28–39** | **`get_current_user()` / `get_current_workspace()`** — Reads `user_id` / `workspace_id` from the session cookie and fetches the full record from `platform_store`. | Abstraction helpers so every route doesn't repeat this lookup logic. |
| **42–50** | **`require_auth` decorator** — Returns 401 if the user is not logged in. | Applied to workspace-specific routes that only make sense for authenticated users. |
| **53–93** | **Workspace session hydration / persistence** — `hydrate_session_from_workspace()` restores agent state from the latest workspace snapshot. `persist_workspace_session()` saves agent state back and logs audit events. | Enables "pick up where you left off" — when a user logs back in, their budget, products, and approval settings are restored from the workspace snapshot. |
| **95–105** | **`serialize_session_state()`** — Converts the in-memory session dict to a safe JSON-serialisable subset (last 20 actions, last 8 products, last 10 conversation turns). | Prevents the response payload from growing unbounded as the conversation continues. |
| **107–646** | **`HTML_PAGE` (legacy inline HTML)** — A complete single-page app embedded as a Python string. Contains the old UI with sidebar, chat, analytics dashboard, and inline JavaScript. | This was the original prototype UI. It is **no longer served** (the `home()` route now uses `render_template('index.html')` instead), but it remains in the codebase as a fallback reference. |
| **648–654** | **`/` and `/favicon.ico` routes** — Serves the main HTML page and returns an empty 204 for favicon requests. | The `render_template('index.html')` call serves the new refactored frontend from `templates/index.html`. The favicon route prevents 404 noise in logs. |
| **656–714** | **Auth routes (`/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`)** — Registration creates a user + default workspace. Login authenticates and hydrates session. Logout clears session. `/me` returns current auth state. | Full user authentication flow using password hashing (Werkzeug). No external auth provider needed. |
| **716–798** | **Workspace CRUD + Task CRUD + Audit + Dashboard routes** — `GET/POST /api/workspaces`, `GET/PUT /api/workspace/current`, `GET/POST/PUT /api/workspace/current/tasks`, `GET /api/workspace/current/audit`, `GET /api/workspace/current/dashboard`. | These routes power the Task Board, Audit Trail, and Business Snapshot panels in the frontend. Everything is persisted to `platform_store.json`. |
| **800–810** | **`/api/session`** — Returns the serialised session state, DB connection status, auth status, current user, and current workspace. | Called on every page load to hydrate the entire frontend UI in one request. |
| **812–848** | **`/chat` (POST)** — The main chat endpoint. Extracts the message, calls `get_agent_response()` from `agent.py`, records usage and audit events, persists the workspace session, and returns the AI response + agent type + updated session. | This is the core interaction loop. The multi-agent orchestrator decides which sub-agent handles the query and returns a tailored response. |
| **850–862** | **`/set-budget` (POST)** — Updates budget and approval level. Records usage and persists workspace. | Called from the sidebar budget input and approval mode buttons. |
| **864–901** | **AlloyDB API endpoints** — `/health`, `/api/db/health`, `/api/history`, `/api/products`, `/api/products/save`, `/api/profile`. | These expose the AlloyDB data layer to the frontend. They gracefully return empty results if the database is unavailable. |
| **903–905** | **`if __name__ == '__main__'`** — Starts Flask's dev server on `0.0.0.0:8080`. | In production, Gunicorn replaces this. The `host='0.0.0.0'` makes it accessible from outside the container. |

---

### `agent.py` — Multi-Agent Orchestrator & Business Logic

**Lines:** 524 | **Size:** ~23 KB | **Role:** The brain of the application — contains the AI agents, Google Trends integration, profit calculators, supplier data, and Telegram notification triggers.

#### Key Sections

| Lines | What It Does | Why |
|---|---|---|
| **1–26** | **Imports** — Loads Gemini SDK, browser agent, Telegram helpers, pytrends, and standard libraries. | Brings together all external services the agent needs. |
| **28–32** | **API keys & Gemini client** — Reads `GEMINI_API_KEY` from env, initialises the `genai.Client`. | If the key is missing, `client` is `None` and the system falls back to rule-based responses instead of crashing. |
| **34–53** | **Session store** — In-memory dictionary keyed by session ID. `get_session_data()` returns or creates a session with default values: budget=0, spent=0, approval_level=confirm, empty actions/products/conversation lists. | This is the ephemeral state for each user. It lives in server memory and can be snapshot-saved to workspace JSON or AlloyDB for persistence. |
| **56–63** | **`_run_in_background()`** — Runs a function in a daemon thread. | Used for fire-and-forget operations (DB writes, Telegram sends) that should never block the HTTP response. |
| **66–89** | **Persistence helpers** — `_persist_trending_products()`, `_persist_conversation()`, `_persist_profile()` — silently write to AlloyDB via `db_manager`. | These run in background threads so the chat response is fast even when AlloyDB is slow or down. |
| **93–96** | **`send_telegram()` wrapper** — Calls `send_telegram_async()` from `telegram_fix.py`. | Legacy compatibility — older code in this file calls `send_telegram()`, which now delegates to the fixed async version. |
| **100–142** | **Google Trends integration** — `get_real_trends()` queries pytrends for real-time data. If `ENABLE_PYTRENDS` is not "true", it returns curated fallback lists per region (IN/US/GB). `get_trending_products()` adds city-level boosting (Delhi, Mumbai, Bangalore, NYC, London). | Pytrends is unreliable in production (rate-limited, CAPTCHAs), so fallback data ensures the app always returns useful results. City boosting personalises the response. |
| **147–161** | **`calculate_profit()`** — Computes profit per unit, total profit, margin %, ROI %, and a verdict (Excellent/Good/Risky/Not recommended). | Core business tool — users ask "calculate profit for cost 200, selling 599, 50 units" and get a structured analysis. |
| **163–169** | **`get_suppliers()`** — Returns a hardcoded list of 4 suppliers with name, URL, price range, shipping days, rating, and MOQ. | Static data that simulates a supplier database. In a production version this would query a real API. |
| **171–184** | **`analyze_budget()`** — Splits the user's budget across products (60% inventory, 30% marketing, 10% reserve) and recommends a testing strategy based on budget size. | Helps beginners understand how to allocate capital for a dropshipping business. |
| **186–207** | **`request_approval()`** — Checks approval level. If "auto", returns True. Otherwise sends a Telegram notification asking for YES/NO and logs the action as "pending". | Part of the approval gate system — users can set "confirm each action" or "full auto within budget". |
| **212–273** | **`build_context()`** — Builds a rich prompt for the Gemini model by detecting intent keywords and injecting real data. Adds trending products, supplier lists, profit calculator availability, budget analysis, and product research results into the context. | This is the "MCP" (Model Context Protocol) pattern — instead of the model guessing, we inject verified data into the prompt so it generates accurate, grounded responses. |
| **276–298** | **Utility helpers** — `_extract_numbers()` parses numbers from text, `_format_currency()` formats amounts, `_product_hint()` returns marketing tips per product. | Small pure functions that keep the main logic clean. |
| **301–414** | **`_build_rule_based_response()`** — A complete fallback response engine that handles greetings, roadmap requests, trend queries, supplier queries, profit calculations, budget planning, and product research **without calling Gemini at all**. | If the API key is missing or the Gemini API fails, users still get structured, useful responses. This is the resilience layer. |
| **419–497** | **`MultiAgentOrchestrator` class** — The core orchestration engine: |
| | `_detect_agent(message)` — keyword-based routing to one of 4 agents | Decides which specialist handles the query |
| | `_trend_agent(context)` — calls Gemini with "You are the Trend Specialist Agent" system prompt | Focused expertise improves response quality |
| | `_supplier_agent(context)` — calls Gemini with supplier-focused system prompt | Same pattern |
| | `_finance_agent(context)` — calls Gemini with finance/profit system prompt | Same pattern |
| | `_general_agent(context)` — calls Gemini with general dropshipping assistant prompt | Catch-all for strategy, roadmaps, etc. |
| | `_fallback_response()` — delegates to rule-based engine | Graceful degradation |
| | `process(message, session_id)` — full pipeline: detect agent → build context → call Gemini (or fallback) → persist conversation → update session state | Single entry point for all chat interactions |
| **500–523** | **Module-level init** — Creates the singleton `orchestrator`, fires a startup Telegram notification, and exposes `get_agent_response()` and `set_budget()` as the public API. | These are the functions imported by `app.py`. |

---

### `database.py` — AlloyDB Integration & ORM Models

**Lines:** 511 | **Size:** ~19 KB | **Role:** Manages the PostgreSQL (AlloyDB) connection and provides CRUD operations for conversations, products, user profiles, and budget transactions.

#### ORM Models

| Model | Table | Columns | Purpose |
|---|---|---|---|
| `Conversation` | `conversations` | `id` (UUID), `session_id`, `agent_type`, `user_message`, `ai_response`, `tokens_used`, `created_at`, `extra_data` (JSONB) | Stores every chat exchange for history and analytics |
| `Product` | `products` | `id`, `name`, `category`, `supplier_url`, `cost_price`, `selling_price`, `profit_margin`, `trend_score`, `is_active`, `research_data` (JSONB), `embedding` (Text), `created_at`, `updated_at` | Product catalog with computed margins and vector embeddings |
| `UserProfile` | `user_profiles` | `id`, `session_id` (unique), `budget_total`, `budget_spent`, `approval_level`, `preferences` (JSONB), `created_at`, `last_active` | Per-session user configuration |
| `BudgetTransaction` | `budget_transactions` | `id`, `session_id`, `amount`, `category`, `description`, `approved`, `created_at` | Audit trail for all budget-related actions |

#### `DatabaseManager` Class

| Method | What It Does | Why |
|---|---|---|
| `_build_connection_string()` | Reads `ALLOYDB_HOST/PORT/DATABASE/USER/PASSWORD` from env and builds a `postgresql+pg8000://` URL | Keeps connection config centralised and env-driven |
| `_init_db()` | Creates SQLAlchemy engine with connection pooling (pool_size=5, max_overflow=10, pool_recycle=1800, pre_ping=True). Optionally creates tables. | Pool recycle prevents stale connections. Pre-ping detects broken connections before use. |
| `_create_tables()` | Creates all ORM tables, enables `pgvector` extension, adds a `vector(768)` column and IVFFlat index to `products` | Enables semantic similarity search on product embeddings |
| `_ensure_initialized()` | Lazy init with 30-second backoff between retry attempts | Prevents connection storms when AlloyDB is temporarily down |
| `save_conversation()` | Inserts a conversation row, commits, returns the UUID | Every chat exchange is persisted for the History tab |
| `get_conversation_history()` | Queries conversations by session_id, returns most recent N | Powers the Conversation History tab |
| `save_product()` | Auto-calculates profit_margin from cost/selling price, inserts product | Trending products are saved for future reference |
| `get_products()` | Filter by category, min_margin; sort by trend_score | Powers the Products API endpoint |
| `find_similar_products()` | pgvector cosine distance search using `<=>` operator | Semantic product search (e.g., "find products similar to smart watch") |
| `get_or_create_profile()` | Upsert pattern for user profiles | Ensures every session has a profile record |
| `update_profile()` | Updates any profile fields dynamically | Budget and approval level changes |
| `log_transaction()` | Records a budget transaction and updates spent amount on approval | Financial audit trail |
| `health_check()` | Runs `SELECT COUNT(*) FROM conversations` and reports status | Powers the DB health badge in the header |

**Graceful degradation:** Every method catches exceptions, calls `_mark_unavailable()` to reset the connection, and returns `None` or `[]`. The app never crashes because of a database outage.

---

### `platform_store.py` — Local JSON Workspace Store

**Lines:** 319 | **Size:** ~12 KB | **Role:** A thread-safe, file-based persistence layer for user accounts, workspaces, tasks, audit events, usage metrics, and session snapshots — all stored in a single `data/platform_store.json` file.

#### Why Not Just Use AlloyDB?

AlloyDB requires a cloud database connection. The platform store provides **local-first** functionality — users can register, create workspaces, queue tasks, and track audit events **without any external database**. It makes the app work offline or in development.

#### Data Model (inside JSON file)

```json
{
  "users": [...],
  "workspaces": [...],
  "workspace_snapshots": [...],
  "audit_events": [...],
  "agent_tasks": [...],
  "usage_events": [...]
}
```

#### Key Methods

| Method | What It Does |
|---|---|
| `register_user()` | Hashes password (Werkzeug), creates user + default workspace |
| `authenticate_user()` | Verifies email + password hash, updates `last_login_at` |
| `create_workspace()` | Creates a workspace with country, niche, budget, settings, and default `store_stage: "idea"` |
| `save_workspace_snapshot()` | Saves the full agent session state (budget, products, actions, conversation) — keeps last 200 |
| `get_latest_workspace_snapshot()` | Restores the most recent snapshot for session hydration |
| `append_audit_event()` | Logs timestamped events (workspace.created, chat.completed, budget.updated, etc.) — keeps last 500 |
| `create_task()` / `update_task()` | Task board CRUD (queued → in_progress → completed) |
| `record_usage()` | Tracks usage events (chat_request, budget_update) — keeps last 1000 |
| `get_dashboard_summary()` | Aggregates tasks by status, usage by kind, audit count, product count, budget/spent |

**Thread safety:** All writes go through `_save(mutator)` which acquires a threading lock, reads the JSON file, applies the mutation function, and writes back.

---

### `browser_agent.py` — Product Research & Browser Automation

**Lines:** 78 | **Size:** ~3 KB | **Role:** Provides product research capabilities through supplier data scraping (with fallbacks) and optional AI browser automation.

| Function | Lines | What It Does |
|---|---|---|
| `scrape_aliexpress()` | 12–26 | **Returns fallback data** — constructs 3 mock AliExpress listings with price, orders, rating. Real scraping is disabled because AliExpress blocks automated requests. |
| `search_cj_dropshipping()` | 28–32 | Returns 2 mock CJ Dropshipping results with cost, shipping, and stock. |
| `run_browser_agent()` | 34–50 | **Optional** — Uses the `browser-use` library with LangChain + Gemini to run an AI-driven browser that can actually navigate websites and extract data. Falls back gracefully if `browser-use` isn't installed. |
| `research_product()` | 52–74 | Combines AliExpress and CJ data, calculates recommended selling price (2.8× cost), margin, and generates a profit analysis report with a recommendation. |
| `run_product_research()` | 76–77 | Simple alias for `research_product()` — this is the function imported by `agent.py`. |

---

### `telegram_fix.py` — Telegram Notification Service

**Lines:** 127 | **Size:** ~4 KB | **Role:** A drop-in replacement for Telegram notifications that fixes async/threading issues from the original implementation.

**Why this file exists:** The original code used Python's `asyncio` for Telegram which silently failed inside Flask's synchronous request handlers. This module uses pure `requests.post()` for reliability.

| Function | What It Does |
|---|---|
| `send_telegram(message)` | **Synchronous** — sends a Telegram message via HTTP POST with HTML parse mode. Returns True/False. Respects `TELEGRAM_ENABLED` flag. |
| `send_telegram_async(message)` | **Fire-and-forget** — wraps `send_telegram()` in a daemon thread so it never blocks the HTTP response. |
| `notify_trend_found(product, score, region)` | Sends "📈 Trending Product Found!" alert |
| `notify_budget_approval(item, amount, level)` | Sends "✅ Auto-Approved" or "⏳ Pending Approval" alert |
| `notify_supplier_found(product, supplier, price)` | Sends "🏭 Supplier Found" alert |
| `notify_error(error_msg, context)` | Sends "🚨 DropShip Agent Error" alert |
| `notify_agent_started()` | Sends "🚀 DropShip AI Agent Started" on server boot |

---

### `setup_db.py` — One-Time Database Bootstrap

**Lines:** 69 | **Size:** ~2 KB | **Role:** Run once to create the `dropship_db` database and enable `pgvector` and `uuid-ossp` extensions on AlloyDB.

**How it works:**
1. Connects to the default `postgres` database using `pg8000` (pure Python driver)
2. Checks if `dropship_db` exists — creates it if not
3. Connects to `dropship_db` and enables extensions
4. Prints the environment variable configuration for the user

---

### `templates/index.html` — Frontend HTML Shell

**Lines:** 310 | **Size:** ~17 KB | **Role:** The main frontend — a single-page application served by Flask's `render_template()`.

#### Layout Structure

```
┌────────────────────────────────────────────────────────────────────┐
│ Top Bar: Brand mark + Workspace/Agent/DB status pills             │
├──────────┬─────────────────────────────────────────────────────────┤
│          │ Hero Strip: Operator console tagline + action buttons   │
│  Left    ├────────────────────────────────────────────────────────┤
│  Rail    │ Metrics Grid: Products | Actions | Tasks | Usage       │
│          ├────────────────────────────────────────────────────────┤
│ Account  │ Tab Bar: Command Deck | Analytics | Task Board | Audit │
│ Budget   ├────────────────────────────────────────────────────────┤
│ Workflow │ Tab Panels:                                            │
│ Launchers│   Chat → Assistant console + side panels (queue,       │
│          │          product radar, execution log)                  │
│          │   Analytics → Profit chart + Budget chart + Snapshot    │
│          │   Task Board → Queued | In Progress | Completed        │
│          │   Audit → Timeline + Conversation Memory               │
└──────────┴────────────────────────────────────────────────────────┘
```

---

### `static/app.css` — Frontend Styles

**Lines:** 187 | **Size:** ~9 KB | **Role:** Complete CSS design system for the dark-mode "mission control" UI.

| Section | What It Defines |
|---|---|
| `:root` variables | Color palette (bg, panel, text, muted, accent, accent-2, success, warning, danger), shadow |
| `.ambient` | Decorative gradient orbs with blur for ambient lighting effect |
| `.topbar` | Glassmorphism header with `backdrop-filter: blur(18px)` |
| `.panel` | Glassmorphism card with gradient background and border |
| `.field`, `.composer-input` | Form inputs with focus animation (`translateY(-1px)`) |
| `.primary-btn`, `.ghost-btn` | Button variants with hover lift (`translateY(-2px)`) |
| `.budget-track` | Animated progress bar for budget utilisation |
| `.message-card` | Chat bubbles — user messages get accent gradient, agent messages get outline |
| `.typing-dot` | Bounce animation for typing indicator |
| `.metric-card` | KPI display cards with Space Grotesk numbers |
| `.task-card` | Kanban-style task cards |
| `@media` queries | Responsive breakpoints at 1240px and 760px |

---

### `static/app.js` — Frontend JavaScript Logic

**Lines:** 573 | **Size:** ~20 KB | **Role:** All frontend interactivity — chat, auth, workspace management, task board, charts, and state rendering.

| Function | What It Does |
|---|---|
| `loadSessionState()` | Fetches `/api/session` and hydrates the entire UI (auth, session, conversation, actions, products, DB badge, tasks, dashboard, audit) |
| `sendMessage()` | Posts to `/chat`, shows typing indicator, appends agent response, updates all panels |
| `sendQuick(prompt)` | Pre-fills the chat input and sends — powers all the quick action buttons |
| `registerAccount()` / `loginAccount()` / `logoutAccount()` | Auth flow — calls `/api/auth/*` endpoints |
| `createWorkspaceLocal()` | Prompts for a name, creates a workspace via `/api/workspaces` |
| `setBudget()` / `setApproval()` | Updates budget and approval mode via `/set-budget` |
| `quickTask()` | Creates a task via `/api/workspace/current/tasks` |
| `updateTaskStatus()` | Moves a task between lanes (queued → in_progress → completed) |
| `loadTasks()` / `renderTaskBoard()` | Fetches and renders the Kanban-style task board |
| `loadDashboard()` / `renderDashboardSummary()` | Fetches and renders workspace analytics |
| `loadAudit()` / `renderAudit()` | Fetches and renders the audit trail timeline |
| `loadHistory()` / `renderConversationMemory()` | Renders recent conversation as timeline cards |
| `initCharts()` | Creates Chart.js line chart (profit margins) and doughnut chart (budget allocation) |
| `escapeHtml()` | Prevents XSS by escaping `<>&"'` characters |
| `formatCurrency()` / `formatTime()` / `capitalize()` | Display formatting helpers |

---

### Configuration & DevOps Files

#### `requirements.txt`
Lists all 17 Python dependencies with pinned versions. Used by `pip install -r requirements.txt` and the Dockerfile.

#### `Dockerfile`
```dockerfile
FROM python:3.11-slim          # Slim image for smaller container size
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt  # No pip cache to reduce image size
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--timeout", "120", "app:app"]
```
- **1 worker** — because the app uses in-memory session state. Multiple workers would create separate memory spaces.
- **120s timeout** — Gemini API calls can take 30–45 seconds; the timeout prevents premature kills.

#### `cloudbuild_update.yaml`
Three-step CI/CD pipeline:
1. **Build** — `docker build` with the Artifact Registry tag
2. **Push** — pushes image to `asia-south2-docker.pkg.dev/parth123-415808/dropship-agent/`
3. **Deploy** — `gcloud run deploy` with env vars from `env.yaml`, 1 GB RAM, 1 CPU, 0–3 instances, allow unauthenticated

#### `.env.example` / `env.yaml.example`
Templates showing all required environment variables with placeholder values. Safe to commit (no real secrets).

#### `.gitignore`
Excludes `.env`, `env.yaml`, `env_setup.bat`, `__pycache__/`, `*.db`, `data/`, `.gcloud/`, and OS files.

#### `.dockerignore`
Excludes `.git`, `.gcloud`, secrets files, databases, and Python cache from the Docker build context to keep the image small.

---

## API Endpoints Reference

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | No | Create account — body: `{email, password, full_name}` |
| `POST` | `/api/auth/login` | No | Login — body: `{email, password}` |
| `POST` | `/api/auth/logout` | No | Clear session |
| `GET` | `/api/auth/me` | No | Current auth state |

### Chat & Session

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/chat` | No | Send message to AI agent — body: `{message}` → returns `{response, agent_type, session}` |
| `GET` | `/api/session` | No | Get current session state, DB status, user, workspace |
| `POST` | `/set-budget` | No | Set budget + approval level — body: `{budget, approval_level}` |

### Workspaces

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/workspaces` | Yes | List user's workspaces |
| `POST` | `/api/workspaces` | Yes | Create workspace — body: `{name, country?, niche?, monthly_budget?}` |
| `GET` | `/api/workspace/current` | Yes | Get current workspace + latest snapshot |
| `PUT` | `/api/workspace/current` | Yes | Update current workspace fields |

### Tasks

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/workspace/current/tasks` | Yes | List all tasks in current workspace |
| `POST` | `/api/workspace/current/tasks` | Yes | Create task — body: `{title, task_type, status?, owner_agent?, details?}` |
| `PUT` | `/api/workspace/current/tasks/<id>` | Yes | Update task (e.g., change status) |

### Analytics & Audit

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/workspace/current/audit` | Yes | List audit events |
| `GET` | `/api/workspace/current/dashboard` | Yes | Get aggregated dashboard summary |

### AlloyDB Data

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/api/db/health` | No | Database health check |
| `GET` | `/api/history` | No | Conversation history from AlloyDB |
| `GET` | `/api/products` | No | Products list (filter by `category`, `min_margin`) |
| `POST` | `/api/products/save` | No | Save a product to AlloyDB |
| `GET` | `/api/profile` | No | Get/create user profile from AlloyDB |

### System

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/` | No | Serve the main HTML page |
| `GET` | `/health` | No | App health check (version, agents, DB status) |

---

## Multi-Agent System

The `MultiAgentOrchestrator` routes each user message to one of four specialised Gemini sub-agents:

```
User Message
    │
    ▼
┌─────────────────────┐
│  _detect_agent()    │  Keyword-based routing
└─────────┬───────────┘
          │
    ┌─────┼──────────┬──────────────┐
    ▼     ▼          ▼              ▼
┌──────┐ ┌────────┐ ┌───────────┐ ┌─────────┐
│Trend │ │Supplier│ │ Finance   │ │ General │
│Agent │ │Agent   │ │ Agent     │ │ Agent   │
└──────┘ └────────┘ └───────────┘ └─────────┘
```

| Agent | Trigger Keywords | Specialisation |
|---|---|---|
| **Trend** | trend, trending, popular, hot product, what to sell | Finding and analyzing trending products with market data |
| **Supplier** | supplier, source, vendor, aliexpress | Finding, vetting, and comparing suppliers |
| **Finance** | profit, margin, budget, invest, roi, calculate | Profits, margins, ROI, and budget allocation |
| **General** | (everything else) | Strategy, roadmaps, and general dropshipping advice |

Each agent gets the same enriched context (injected real data) but a different system prompt that focuses its expertise.

---

## Database Schema

```
┌──────────────────┐    ┌──────────────────┐
│  conversations   │    │    products       │
├──────────────────┤    ├──────────────────┤
│ id (UUID PK)     │    │ id (UUID PK)     │
│ session_id       │    │ name             │
│ agent_type       │    │ category         │
│ user_message     │    │ supplier_url     │
│ ai_response      │    │ cost_price       │
│ tokens_used      │    │ selling_price    │
│ created_at       │    │ profit_margin    │
│ extra_data (JSON)│    │ trend_score      │
└──────────────────┘    │ is_active        │
                        │ research_data(J) │
┌──────────────────┐    │ embedding (text) │
│  user_profiles   │    │ product_embedding│
├──────────────────┤    │   (vector 768)   │
│ id (UUID PK)     │    │ created_at       │
│ session_id (UQ)  │    │ updated_at       │
│ budget_total     │    └──────────────────┘
│ budget_spent     │
│ approval_level   │    ┌──────────────────┐
│ preferences (J)  │    │budget_transactions│
│ created_at       │    ├──────────────────┤
│ last_active      │    │ id (UUID PK)     │
└──────────────────┘    │ session_id       │
                        │ amount           │
                        │ category         │
                        │ description      │
                        │ approved         │
                        │ created_at       │
                        └──────────────────┘
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | **Yes** | Google Gemini 2.5 Flash API key |
| `ALLOYDB_HOST` | No | AlloyDB/PostgreSQL server IP |
| `ALLOYDB_PORT` | No | Database port (default: 5432) |
| `ALLOYDB_DATABASE` | No | Database name (default: dropship_db) |
| `ALLOYDB_USER` | No | Database user (default: postgres) |
| `ALLOYDB_PASSWORD` | No | Database password |
| `TELEGRAM_ENABLED` | No | Set to "true" to enable Telegram notifications |
| `TELEGRAM_TOKEN` | No | Telegram Bot API token |
| `TELEGRAM_CHAT_ID` | No | Telegram chat ID to send notifications to |
| `GOOGLE_CLOUD_PROJECT` | No | GCP project ID (for Cloud Run) |
| `GOOGLE_CLOUD_REGION` | No | GCP region (default: asia-south2) |
| `FLASK_SECRET_KEY` | No | Flask session secret (default provided) |
| `ENABLE_PYTRENDS` | No | Set to "true" to use live Google Trends (default: fallback data) |
| `AUTO_CREATE_DB_SCHEMA` | No | Set to "true" to auto-create tables on DB connect |
| `DB_CONNECT_TIMEOUT` | No | Database connection timeout in seconds (default: 5) |

---

## Getting Started

### Prerequisites
- Python 3.11+
- (Optional) Google Cloud account with AlloyDB
- (Optional) Telegram Bot token

### Local Development

```bash
# 1. Clone the repository
git clone https://github.com/gitzboy1/Dropship-agent.git
cd Dropship-agent

# 2. Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env and add your GEMINI_API_KEY (minimum required)

# 5. (Optional) Set up AlloyDB
python setup_db.py

# 6. Run the app
python app.py
# Server starts at http://localhost:8080
```

---

## Deployment (Google Cloud Run)

```bash
# 1. Configure env.yaml with your secrets
copy env.yaml.example env.yaml
# Edit env.yaml

# 2. Submit to Cloud Build (builds, pushes, and deploys)
gcloud builds submit --config=cloudbuild_update.yaml

# The app will be live at:
# https://dropship-agent-<hash>-<region>.a.run.app
```

### Cloud Run Configuration (from cloudbuild_update.yaml)
- **Region:** asia-south2
- **Memory:** 1 GB
- **CPU:** 1
- **Min instances:** 0 (scales to zero)
- **Max instances:** 3
- **Timeout:** 120s (via Gunicorn)
- **Authentication:** Allow unauthenticated

---

*Built with ❤️ using Google Gemini 2.5 Flash, Flask, AlloyDB, and Cloud Run.*
