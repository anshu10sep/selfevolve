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
        {"id": str(uuid.uuid4()), "name": "CTO Agent", "role": "CTO", "type": "EXECUTIVE", "status": "ACTIVE", "trust_weight": 1.0, "brier_score": None, "tasks_today": 0, "cost_today": 0.0, "last_activity": None},
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


active_connections: list[WebSocket] = []


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
    for agent in system_state["agents"]:
        if agent.get("id") == agent_id:
            return agent
    raise HTTPException(status_code=404, detail="Agent not found")


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
