"""
SelfEvolve Dashboard API

FastAPI application providing the owner interface for monitoring
and controlling the entire trading system. Also serves as the
health check endpoint for Docker.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import structlog

logger = structlog.get_logger(component="dashboard_api")

app = FastAPI(
    title="SelfEvolve Dashboard",
    description="Owner interface for the autonomous self-evolving trading system",
    version="1.0.0",
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
# In-memory state (in production, reads from Redis/Postgres)
# ════════════════════════════════════════════════════════════════════
system_state: dict[str, Any] = {
    "status": "INITIALIZING",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "portfolio": {
        "total_equity": 100.0,
        "settled_cash": 100.0,
        "daily_pnl": 0.0,
        "total_api_cost_today": 0.0,
        "positions": {},
        "drawdown_pct": 0.0,
    },
    "agents": [],
    "recent_trades": [],
    "evolution_events": [],
    "active_bugs": [],
    "circuit_breaker": {"tripped": False, "trip_count": 0},
    "hcf_active": False,
}

# Active WebSocket connections for real-time updates
active_connections: list[WebSocket] = []


# ════════════════════════════════════════════════════════════════════
# HEALTH & STATUS
# ════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """Docker health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_status": system_state["status"],
    }


@app.get("/api/status")
async def get_system_status():
    """Get complete system status."""
    return system_state


# ════════════════════════════════════════════════════════════════════
# PORTFOLIO
# ════════════════════════════════════════════════════════════════════

@app.get("/api/portfolio")
async def get_portfolio():
    """Get current portfolio state."""
    return system_state["portfolio"]


@app.get("/api/portfolio/history")
async def get_portfolio_history():
    """Get portfolio value history for charting."""
    return {"history": [], "message": "Historical data populated after first trade"}


# ════════════════════════════════════════════════════════════════════
# AGENTS
# ════════════════════════════════════════════════════════════════════

@app.get("/api/agents")
async def get_agents():
    """Get all agents and their health metrics."""
    return {"agents": system_state["agents"]}


@app.get("/api/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Get detailed info for a specific agent."""
    for agent in system_state["agents"]:
        if agent.get("agent_id") == agent_id:
            return agent
    return {"error": "Agent not found"}


@app.get("/api/agents/hierarchy")
async def get_agent_hierarchy():
    """Get the agent hierarchy tree."""
    return {"hierarchy": system_state.get("hierarchy", {})}


# ════════════════════════════════════════════════════════════════════
# TRADES
# ════════════════════════════════════════════════════════════════════

@app.get("/api/trades")
async def get_recent_trades():
    """Get recent trade history."""
    return {"trades": system_state["recent_trades"]}


@app.get("/api/trades/{trade_id}")
async def get_trade_detail(trade_id: str):
    """Get full trade detail including debate transcript and audit trail."""
    return {"trade_id": trade_id, "detail": "Trade detail populated after execution"}


# ════════════════════════════════════════════════════════════════════
# EVOLUTION
# ════════════════════════════════════════════════════════════════════

@app.get("/api/evolution")
async def get_evolution_events():
    """Get evolution history."""
    return {"events": system_state["evolution_events"]}


@app.get("/api/evolution/timeline")
async def get_evolution_timeline():
    """Get visual evolution timeline data."""
    return {"timeline": []}


# ════════════════════════════════════════════════════════════════════
# BUGS
# ════════════════════════════════════════════════════════════════════

@app.get("/api/bugs")
async def get_bugs():
    """Get all bug reports."""
    return {"bugs": system_state["active_bugs"]}


@app.get("/api/bugs/summary")
async def get_bug_summary():
    """Get bug statistics."""
    bugs = system_state["active_bugs"]
    return {
        "total": len(bugs),
        "open": len([b for b in bugs if b.get("status") == "OPEN"]),
        "in_progress": len([b for b in bugs if b.get("status") == "IN_PROGRESS"]),
        "resolved": len([b for b in bugs if b.get("status") == "RESOLVED"]),
    }


# ════════════════════════════════════════════════════════════════════
# AUDIT
# ════════════════════════════════════════════════════════════════════

@app.get("/api/audit")
async def get_audit_trail():
    """Get the audit trail."""
    return {"audit_events": []}


@app.get("/api/costs")
async def get_cost_breakdown():
    """Get LLM API cost breakdown by agent and model."""
    return {
        "total_cost_today": system_state["portfolio"].get("total_api_cost_today", 0),
        "breakdown_by_agent": {},
        "breakdown_by_model": {},
    }


# ════════════════════════════════════════════════════════════════════
# OWNER CHAT
# ════════════════════════════════════════════════════════════════════

@app.post("/api/chat")
async def owner_chat(message: dict):
    """
    Chat with the Master Agent.
    
    The owner can ask anything about the system and get
    a comprehensive response from the Master Agent.
    """
    user_message = message.get("message", "")
    return {
        "response": f"Master Agent received: '{user_message}'. "
                    "Full LLM integration enables natural language interaction.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════════════
# WEBSOCKET (Real-time updates)
# ════════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time WebSocket for dashboard updates."""
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Send periodic status updates
            await websocket.send_json({
                "type": "status_update",
                "data": system_state,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        active_connections.remove(websocket)


# ════════════════════════════════════════════════════════════════════
# CONTROL
# ════════════════════════════════════════════════════════════════════

@app.post("/api/control/pause")
async def pause_trading():
    """Pause all trading activity."""
    system_state["status"] = "PAUSED"
    return {"status": "PAUSED", "message": "Trading paused by owner"}


@app.post("/api/control/resume")
async def resume_trading():
    """Resume trading activity."""
    system_state["status"] = "RUNNING"
    return {"status": "RUNNING", "message": "Trading resumed by owner"}


@app.post("/api/control/hcf-reset")
async def reset_hcf():
    """Reset the Halt-and-Catch-Fire protocol."""
    system_state["hcf_active"] = False
    return {"status": "HCF_RESET", "message": "HCF protocol deactivated by owner"}


# Static files (frontend)
try:
    app.mount("/", StaticFiles(directory="dashboard/frontend", html=True), name="frontend")
except Exception:
    pass  # Frontend may not exist yet
