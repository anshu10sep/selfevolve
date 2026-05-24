"""
SelfEvolve Jarvis Command Center — API

Full-featured FastAPI application providing the owner interface
for monitoring, controlling, and intervening in the trading system.
Includes HITL (Human-in-the-Loop) controls for priority issue processing.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import structlog

logger = structlog.get_logger(component="dashboard_api")

app = FastAPI(
    title="Jarvis Command Center",
    description="Owner interface for the SelfEvolve autonomous self-evolving trading system",
    version="2.0.0",
)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ════════════════════════════════════════════════════════════════════

class HITLAction(BaseModel):
    """Human-in-the-loop action on an issue."""
    issue_id: str
    action: str  # "APPROVE", "REJECT", "ESCALATE", "FORCE_FIX", "DEFER"
    notes: Optional[str] = None
    priority: Optional[str] = None  # "CRITICAL", "HIGH", "MEDIUM", "LOW"

class ChatMessage(BaseModel):
    message: str

class ControlAction(BaseModel):
    action: str
    params: Optional[dict] = None


# ════════════════════════════════════════════════════════════════════
# IN-MEMORY STATE (production reads from Redis/Postgres)
# ════════════════════════════════════════════════════════════════════

system_state: dict[str, Any] = {
    "status": "RUNNING",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "uptime_hours": 0,
    "current_phase": "IDLE",
    "portfolio": {
        "total_equity": 100.0,
        "settled_cash": 100.0,
        "unsettled_cash": 0.0,
        "daily_pnl": 0.0,
        "total_pnl": 0.0,
        "total_api_cost_today": 0.0,
        "total_api_cost_alltime": 0.0,
        "net_pnl": 0.0,
        "positions": {},
        "drawdown_pct": 0.0,
        "available_tranches": 10,
        "locked_tranches": 0,
        "settling_tranches": 0,
    },
    "agents": [
        {"id": str(uuid.uuid4()), "name": "Jarvis", "role": "MASTER", "type": "EXECUTIVE", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": datetime.now(timezone.utc).isoformat()},
        {"id": str(uuid.uuid4()), "name": "CTO — Stocks", "role": "CTO", "type": "EXECUTIVE", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None, "division": "stocks"},
        {"id": str(uuid.uuid4()), "name": "CTO — Crypto", "role": "CTO_CRYPTO", "type": "EXECUTIVE", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None, "division": "crypto"},
        {"id": str(uuid.uuid4()), "name": "CSO Agent", "role": "CSO", "type": "EXECUTIVE", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "QA Agent", "role": "QA", "type": "MANAGER", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Developer Agent", "role": "DEVELOPER", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Product Agent", "role": "PRODUCT", "type": "MANAGER", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Fundamental Analyst", "role": "FUNDAMENTAL_ANALYST", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": 0.22, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Technical Analyst", "role": "TECHNICAL_ANALYST", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": 0.19, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Sentiment Analyst", "role": "SENTIMENT_ANALYST", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": 0.28, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Macro Analyst", "role": "MACRO_ANALYST", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": 0.24, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Bull Agent", "role": "BULL", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Bear Agent", "role": "BEAR", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Judge Agent", "role": "JUDGE", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": 0.18, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Meta-Review Agent", "role": "META_REVIEW", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Journaling Agent", "role": "JOURNALING", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Auditor Agent", "role": "AUDITOR", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Model Orchestrator", "role": "MODEL_ORCHESTRATOR", "type": "SPECIALIST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
        {"id": str(uuid.uuid4()), "name": "Crypto Analyst", "role": "CRYPTO_ANALYST", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None, "division": "crypto"},
        {"id": str(uuid.uuid4()), "name": "Crypto Sentiment", "role": "CRYPTO_SENTIMENT", "type": "ANALYST", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None, "division": "crypto"},
    ],
    "recent_trades": [],
    "evolution_events": [],
    "roadmap": [],
    "daily_progress": [],
    "bugs": [],
    "hitl_queue": [],
    "circuit_breaker": {"tripped": False, "trip_count": 0},
    "hcf_active": False,
    "system_audit": {
        "readiness_score": 0.81,
        "total_files": 88,
        "total_lines": 8975,
        "critical_findings": 0,
        "high_findings": 0,
    },
    "model_config": {
        "current_model": "gemini-3.1-pro",
        "efficient_tier": "gemini-3.1-pro",
        "premium_tier": "gemini-3.1-pro",
        "subscriptions": {"gemini": True, "openai": False, "anthropic": False},
    },
}

# ── DATABASE INITIALIZATION ───────────────────────────────────────
# Production-ready SQLAlchemy DB (SQLite now, Postgres later)
from persistence.db import init_db, migrate_json_to_db, sync_state_from_db

init_db()               # Create tables if they don't exist
migrate_json_to_db()    # One-time: import any existing state.json
sync_state_from_db(system_state)  # Load bugs, FRs, trades into memory

logger.info("database_ready", bugs=len(system_state["bugs"]),
            frs=len(system_state.get("feature_requests", [])))


active_connections: list[WebSocket] = []


# ════════════════════════════════════════════════════════════════════
# ALPACA LIVE SYNC
# ════════════════════════════════════════════════════════════════════

async def sync_alpaca_portfolio():
    """Fetch live portfolio data from Alpaca and update system_state."""
    try:
        from broker.alpaca_client import AlpacaClient
        client = AlpacaClient()
        account = await client.get_account()
        positions_raw = await client.get_positions()
        await client.close()

        equity = float(account.get("equity", 0))
        cash = float(account.get("cash", 0))
        buying_power = float(account.get("buying_power", 0))
        last_equity = float(account.get("last_equity", equity))
        daily_pnl = equity - last_equity

        positions = {}
        for pos in positions_raw:
            ticker = pos.get("symbol", "")
            positions[ticker] = {
                "ticker": ticker,
                "quantity": float(pos.get("qty", 0)),
                "avg_entry_price": float(pos.get("avg_entry_price", 0)),
                "current_price": float(pos.get("current_price", 0)),
                "market_value": float(pos.get("market_value", 0)),
                "unrealized_pnl": float(pos.get("unrealized_pl", 0)),
                "side": pos.get("side", "long"),
            }

        # Calculate tranches based on actual equity
        tranche_size = equity / 10.0
        locked_count = len(positions)

        system_state["portfolio"] = {
            "total_equity": equity,
            "settled_cash": cash,
            "unsettled_cash": max(0, equity - cash - sum(p.get("market_value", 0) for p in positions.values())),
            "buying_power": buying_power,
            "daily_pnl": daily_pnl,
            "total_pnl": equity - 100000.0,  # vs starting capital
            "total_api_cost_today": system_state["portfolio"].get("total_api_cost_today", 0),
            "total_api_cost_alltime": system_state["portfolio"].get("total_api_cost_alltime", 0),
            "net_pnl": daily_pnl,
            "positions": positions,
            "drawdown_pct": max(0, (last_equity - equity) / last_equity * 100) if last_equity > 0 else 0,
            "available_tranches": max(0, 10 - locked_count),
            "locked_tranches": locked_count,
            "settling_tranches": 0,
            "tranche_size": tranche_size,
            "account_status": account.get("status", "UNKNOWN"),
            "account_number": account.get("account_number", ""),
            "last_synced": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "alpaca_synced",
            equity=equity,
            cash=cash,
            positions=len(positions),
            daily_pnl=daily_pnl,
        )

    except Exception as e:
        logger.error("alpaca_sync_failed", error=str(e))


@app.on_event("startup")
async def startup_sync():
    """Sync with Alpaca on dashboard startup."""
    await sync_alpaca_portfolio()


# ════════════════════════════════════════════════════════════════════
# HEALTH & STATUS
# ════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_status": system_state["status"],
    }


@app.get("/api/status")
async def get_system_status():
    # Sync live data from Alpaca
    await sync_alpaca_portfolio()
    # Compute uptime
    started = datetime.fromisoformat(system_state["started_at"])
    uptime = datetime.now(timezone.utc) - started
    system_state["uptime_hours"] = round(uptime.total_seconds() / 3600, 1)
    return system_state


# ════════════════════════════════════════════════════════════════════
# PORTFOLIO
# ════════════════════════════════════════════════════════════════════

@app.get("/api/portfolio")
async def get_portfolio():
    await sync_alpaca_portfolio()
    return system_state["portfolio"]


@app.get("/api/portfolio/history")
async def get_portfolio_history():
    return {"history": system_state.get("daily_progress", [])}


# ════════════════════════════════════════════════════════════════════
# AGENTS
# ════════════════════════════════════════════════════════════════════

@app.get("/api/agents")
async def get_agents():
    return {"agents": system_state["agents"]}


@app.get("/api/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Get detailed info for a specific agent including goals, skills, and config."""
    agent = None
    for a in system_state["agents"]:
        if a.get("id") == agent_id:
            agent = a
            break
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Map role to skills directory name
    role_to_dir = {
        "MASTER": "jarvis", "CTO": "cto", "CTO_CRYPTO": "cto_crypto", "CSO": "cso", "QA": "qa",
        "DEVELOPER": "developer", "PRODUCT": "product",
        "FUNDAMENTAL_ANALYST": "fundamental_analyst",
        "TECHNICAL_ANALYST": "technical_analyst",
        "SENTIMENT_ANALYST": "sentiment_analyst",
        "MACRO_ANALYST": "macro_analyst",
        "BULL": "bull", "BEAR": "bear", "JUDGE": "judge",
        "META_REVIEW": "meta_review", "JOURNALING": "journaling",
        "AUDITOR": "auditor", "MODEL_ORCHESTRATOR": "model_orchestrator",
        "CRYPTO_ANALYST": "crypto_analyst", "CRYPTO_SENTIMENT": "crypto_sentiment",
    }

    role = agent.get("role", "")
    skills_dir_name = role_to_dir.get(role, role.lower())
    skills_path = os.path.join(os.path.dirname(__file__), "..", "..", "agents", "skills", skills_dir_name)

    # Read goals.md
    goals_text = ""
    goals_file = os.path.join(skills_path, "goals.md")
    try:
        with open(goals_file, "r") as f:
            goals_text = f.read()
    except FileNotFoundError:
        goals_text = "_No goals.md found for this agent._"

    # List skill files
    skill_files = []
    try:
        for fname in sorted(os.listdir(skills_path)):
            if fname.endswith(".py") and fname != "__init__.py":
                skill_files.append(fname.replace(".py", "").replace("_", " ").title())
    except FileNotFoundError:
        pass

    # Build detailed response
    return {
        **agent,
        "goals": goals_text,
        "skills": skill_files,
        "skills_dir": skills_dir_name,
        "model": "gemini-3.1-pro",
        "metrics": {
            "trust_weight": agent.get("trust_weight", 1.0),
            "brier_score": agent.get("brier_score"),
            "tasks_today": agent.get("tasks_today", 0),
            "tasks_alltime": agent.get("tasks_alltime", 0),
            "cost_today": agent.get("cost_today", 0.0),
            "cost_alltime": agent.get("cost_alltime", 0.0),
            "tokens_today": agent.get("tokens_today", 0),
            "last_activity": agent.get("last_activity"),
            "consecutive_failures": agent.get("consecutive_failures", 0),
            "evolution_count": agent.get("evolution_count", 0),
        },
    }


@app.get("/api/agents/hierarchy")
async def get_agent_hierarchy():
    # Build hierarchy from agent data
    hierarchy = {"name": "Jarvis", "role": "MASTER", "children": []}
    executives = [a for a in system_state["agents"] if a["type"] == "EXECUTIVE" and a["role"] != "MASTER"]
    managers = [a for a in system_state["agents"] if a["type"] == "MANAGER"]
    analysts = [a for a in system_state["agents"] if a["type"] == "ANALYST"]
    specialists = [a for a in system_state["agents"] if a["type"] == "SPECIALIST"]
    for e in executives:
        hierarchy["children"].append({"name": e["name"], "role": e["role"], "children": []})
    for m in managers:
        hierarchy["children"].append({"name": m["name"], "role": m["role"], "children": []})
    hierarchy["children"].append({"name": "Analysts", "role": "GROUP", "children": [{"name": a["name"], "role": a["role"]} for a in analysts]})
    hierarchy["children"].append({"name": "Specialists", "role": "GROUP", "children": [{"name": s["name"], "role": s["role"]} for s in specialists]})
    return {"hierarchy": hierarchy}


# ════════════════════════════════════════════════════════════════════
# TRADES
# ════════════════════════════════════════════════════════════════════

@app.get("/api/trades")
async def get_recent_trades():
    return {"trades": system_state["recent_trades"]}


@app.get("/api/trades/{trade_id}")
async def get_trade_detail(trade_id: str):
    for t in system_state["recent_trades"]:
        if t.get("id") == trade_id:
            return t
    return {"trade_id": trade_id, "detail": "Trade not found"}


# ════════════════════════════════════════════════════════════════════
# EVOLUTION & ROADMAP
# ════════════════════════════════════════════════════════════════════

@app.get("/api/evolution")
async def get_evolution_events():
    return {"events": system_state["evolution_events"]}


@app.get("/api/roadmap")
async def get_roadmap():
    """Get Jarvis's current evolution roadmap."""
    try:
        from agents.skills.jarvis.agent_planning import AgentPlanner
        planner = AgentPlanner()
        tasks = planner.plan_next_cycle()
        return {
            "tasks": [
                {
                    "title": t.title,
                    "description": t.description,
                    "priority": t.priority,
                    "estimated_hours": t.estimated_hours,
                    "category": t.category,
                    "status": t.status,
                    "agent_role": t.agent_role,
                }
                for t in tasks
            ],
            "total_estimated_hours": sum(t.estimated_hours for t in tasks),
        }
    except Exception as e:
        return {"tasks": [], "error": str(e)}


@app.get("/api/audit")
async def get_system_audit():
    """Run Jarvis system audit and return results."""
    try:
        from agents.skills.jarvis.system_audit import SystemAuditor
        auditor = SystemAuditor()
        report = auditor.full_audit()
        system_state["system_audit"] = {
            "readiness_score": report.readiness_score,
            "total_files": report.total_files,
            "total_lines": report.total_lines,
            "critical_findings": report.critical_count,
            "high_findings": report.high_count,
        }
        return {
            "readiness_score": report.readiness_score,
            "total_files": report.total_files,
            "total_lines": report.total_lines,
            "agents_with_skills": report.agents_with_skills,
            "agents_with_goals": report.agents_with_goals,
            "test_count": report.test_count,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "location": f.location,
                    "description": f.description,
                }
                for f in report.findings
            ],
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/daily-progress")
async def get_daily_progress():
    """Get daily progression data for charts."""
    return {"progress": system_state.get("daily_progress", [])}


@app.get("/api/velocity")
async def get_velocity():
    """Get development velocity metrics."""
    return {
        "files_per_day": system_state["system_audit"].get("total_files", 0),
        "lines_per_day": system_state["system_audit"].get("total_lines", 0),
        "readiness": system_state["system_audit"].get("readiness_score", 0),
        "bugs_filed": len([b for b in system_state["bugs"] if b.get("status") == "OPEN"]),
        "bugs_resolved": len([b for b in system_state["bugs"] if b.get("status") == "RESOLVED"]),
        "evolution_events": len(system_state["evolution_events"]),
    }


# ════════════════════════════════════════════════════════════════════
# BUGS
# ════════════════════════════════════════════════════════════════════

@app.get("/api/bugs")
async def get_bugs():
    return {"bugs": system_state["bugs"]}


@app.get("/api/bugs/summary")
async def get_bug_summary():
    bugs = system_state["bugs"]
    return {
        "total": len(bugs),
        "open": len([b for b in bugs if b.get("status") == "OPEN"]),
        "in_progress": len([b for b in bugs if b.get("status") == "IN_PROGRESS"]),
        "resolved": len([b for b in bugs if b.get("status") == "RESOLVED"]),
        "critical": len([b for b in bugs if b.get("severity") == "CRITICAL"]),
        "high": len([b for b in bugs if b.get("severity") == "HIGH"]),
    }


# ════════════════════════════════════════════════════════════════════
# HITL — HUMAN IN THE LOOP
# ════════════════════════════════════════════════════════════════════

@app.get("/api/hitl/queue")
async def get_hitl_queue():
    """Get all items pending human review."""
    return {"queue": system_state["hitl_queue"]}


@app.post("/api/hitl/action")
async def process_hitl_action(action: HITLAction):
    """Process a human-in-the-loop action on an issue."""
    # Find the issue in bugs or hitl_queue
    issue_found = False

    # Check bugs
    for bug in system_state["bugs"]:
        if bug.get("id") == action.issue_id:
            issue_found = True
            if action.action == "FORCE_FIX":
                bug["status"] = "IN_PROGRESS"
                bug["priority"] = action.priority or bug.get("priority", "HIGH")
                bug["hitl_notes"] = action.notes
                bug["hitl_action"] = "FORCE_FIX"
                bug["hitl_timestamp"] = datetime.now(timezone.utc).isoformat()
            elif action.action == "APPROVE":
                bug["status"] = "RESOLVED"
                bug["hitl_action"] = "APPROVED"
                bug["hitl_timestamp"] = datetime.now(timezone.utc).isoformat()
            elif action.action == "REJECT":
                bug["status"] = "WONT_FIX"
                bug["hitl_action"] = "REJECTED"
                bug["hitl_notes"] = action.notes
                bug["hitl_timestamp"] = datetime.now(timezone.utc).isoformat()
            elif action.action == "ESCALATE":
                bug["severity"] = "CRITICAL"
                bug["hitl_action"] = "ESCALATED"
                bug["hitl_notes"] = action.notes
                bug["hitl_timestamp"] = datetime.now(timezone.utc).isoformat()
            elif action.action == "DEFER":
                bug["status"] = "DEFERRED"
                bug["hitl_action"] = "DEFERRED"
                bug["hitl_notes"] = action.notes
                bug["hitl_timestamp"] = datetime.now(timezone.utc).isoformat()
            break

    # Check HITL queue
    for item in system_state["hitl_queue"]:
        if item.get("id") == action.issue_id:
            issue_found = True
            item["status"] = "PROCESSED"
            item["human_action"] = action.action
            item["human_notes"] = action.notes
            item["processed_at"] = datetime.now(timezone.utc).isoformat()
            break

    if not issue_found:
        raise HTTPException(status_code=404, detail=f"Issue {action.issue_id} not found")

    # Broadcast update to connected clients
    await _broadcast({"type": "hitl_processed", "issue_id": action.issue_id, "action": action.action})

    return {
        "status": "processed",
        "issue_id": action.issue_id,
        "action": action.action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/hitl/create")
async def create_hitl_issue(issue: dict):
    """Manually create an issue for HITL review."""
    new_issue = {
        "id": str(uuid.uuid4()),
        "title": issue.get("title", "Manual Issue"),
        "description": issue.get("description", ""),
        "severity": issue.get("severity", "MEDIUM"),
        "category": issue.get("category", "MANUAL"),
        "status": "OPEN",
        "created_by": "ADMIN",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    system_state["bugs"].append(new_issue)
    await _broadcast({"type": "new_issue", "issue": new_issue})
    return new_issue


# ════════════════════════════════════════════════════════════════════
# COSTS
# ════════════════════════════════════════════════════════════════════

@app.get("/api/costs")
async def get_cost_breakdown():
    return {
        "total_cost_today": system_state["portfolio"].get("total_api_cost_today", 0),
        "total_cost_alltime": system_state["portfolio"].get("total_api_cost_alltime", 0),
        "model_config": system_state["model_config"],
        "breakdown_by_agent": {a["name"]: a["cost_today"] for a in system_state["agents"]},
    }


# ════════════════════════════════════════════════════════════════════
# OWNER CHAT (Chat with Jarvis)
# ════════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def owner_chat(message: ChatMessage):
    return {
        "response": f"Jarvis received: '{message.message}'. "
                    "Full LLM integration enables natural language interaction.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════════════
# CONTROL ACTIONS
# ════════════════════════════════════════════════════════════════════

@app.post("/api/control/pause")
async def pause_trading():
    system_state["status"] = "PAUSED"
    await _broadcast({"type": "system_paused"})
    return {"status": "PAUSED"}


@app.post("/api/control/resume")
async def resume_trading():
    system_state["status"] = "RUNNING"
    await _broadcast({"type": "system_resumed"})
    return {"status": "RUNNING"}


@app.post("/api/control/hcf-reset")
async def reset_hcf():
    system_state["hcf_active"] = False
    await _broadcast({"type": "hcf_reset"})
    return {"status": "HCF_RESET"}


@app.post("/api/control/force-evolution")
async def force_evolution():
    """Force an immediate evolution cycle."""
    system_state["current_phase"] = "EVOLUTION"
    await _broadcast({"type": "evolution_forced"})
    return {"status": "EVOLUTION_TRIGGERED"}


@app.post("/api/control/force-audit")
async def force_audit():
    """Force a system audit."""
    try:
        from agents.skills.jarvis.system_audit import SystemAuditor
        auditor = SystemAuditor()
        report = auditor.full_audit()
        system_state["system_audit"] = {
            "readiness_score": report.readiness_score,
            "total_files": report.total_files,
            "total_lines": report.total_lines,
            "critical_findings": report.critical_count,
            "high_findings": report.high_count,
        }
        await _broadcast({"type": "audit_complete", "readiness": report.readiness_score})
        return {"status": "AUDIT_COMPLETE", "readiness": report.readiness_score}
    except Exception as e:
        return {"status": "AUDIT_FAILED", "error": str(e)}


# ════════════════════════════════════════════════════════════════════
# WEBSOCKET (Real-time updates)
# ════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.send_json({
                "type": "status_update",
                "data": {
                    "status": system_state["status"],
                    "phase": system_state["current_phase"],
                    "portfolio": system_state["portfolio"],
                    "audit": system_state["system_audit"],
                    "agent_count": len(system_state["agents"]),
                    "active_agents": len([a for a in system_state["agents"] if a["status"] == "ACTIVE"]),
                    "open_bugs": len([b for b in system_state["bugs"] if b.get("status") == "OPEN"]),
                    "hitl_pending": len([h for h in system_state["hitl_queue"] if h.get("status") == "PENDING"]),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        active_connections.remove(websocket)


async def _broadcast(message: dict):
    """Broadcast a message to all connected WebSocket clients."""
    for conn in active_connections:
        try:
            await conn.send_json(message)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# STATIC FILES (Frontend)
# ════════════════════════════════════════════════════════════════════

try:
    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
except Exception:
    pass
