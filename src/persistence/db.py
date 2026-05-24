"""
Persistent Database — SQLAlchemy + SQLite (swap to Postgres with one line)

Production-ready ACID database for all Jarvis state.
Uses SQLAlchemy ORM so migrating to cloud PostgreSQL (Supabase, Neon, RDS)
is a single connection string change.

Current:  sqlite:///data/jarvis.db
Future:   postgresql://user:pass@host:5432/jarvis
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Boolean,
    Text, DateTime, JSON, Enum as SAEnum, Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import structlog

logger = structlog.get_logger(component="database")

# ── Connection ────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "jarvis.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

# For SQLite: check_same_thread=False needed for multi-thread access
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True,  # Auto-reconnect for Postgres
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


# ══════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════

class Bug(Base):
    __tablename__ = "bugs"

    id = Column(String(36), primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    severity = Column(String(20), default="MEDIUM")  # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(String(20), default="OPEN")       # OPEN, IN_PROGRESS, RESOLVED, WONT_FIX
    source = Column(String(100), default="")           # e.g., "FR #abc123"
    assigned_to = Column(String(100), nullable=True)
    pr_url = Column(String(500), nullable=True)
    worker_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_bugs_status", "status"),
        Index("ix_bugs_severity", "severity"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "source": self.source,
            "assigned_to": self.assigned_to,
            "pr_url": self.pr_url,
            "worker_error": self.worker_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class FeatureRequest(Base):
    __tablename__ = "feature_requests"

    id = Column(String(36), primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    analysis = Column(Text, default="")
    status = Column(String(20), default="IN_PROGRESS")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "analysis": self.analysis,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Trade(Base):
    __tablename__ = "trades"

    id = Column(String(36), primary_key=True)
    ticker = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # BUY, SELL
    notional = Column(Float, default=0)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    status = Column(String(20), default="PENDING")  # PENDING, FILLED, CANCELLED
    order_id = Column(String(100), nullable=True)
    division = Column(String(20), default="stocks")  # stocks, crypto
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    analysis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    filled_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_trades_ticker", "ticker"),
        Index("ix_trades_status", "status"),
        Index("ix_trades_division", "division"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "side": self.side,
            "notional": self.notional,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "realized_pnl": self.realized_pnl,
            "status": self.status,
            "order_id": self.order_id,
            "division": self.division,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


class AgentScore(Base):
    __tablename__ = "agent_scores"

    role = Column(String(50), primary_key=True)  # Stable key across restarts
    name = Column(String(100), nullable=False)
    trust_weight = Column(Float, default=1.0)
    brier_score = Column(Float, nullable=True)
    tasks_total = Column(Integer, default=0)
    cost_total = Column(Float, default=0.0)
    last_activity = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "name": self.name,
            "trust_weight": self.trust_weight,
            "brier_score": self.brier_score,
            "tasks_total": self.tasks_total,
            "cost_total": self.cost_total,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
        }


class EvolutionEvent(Base):
    __tablename__ = "evolution_events"

    id = Column(String(36), primary_key=True)
    event_type = Column(String(50), nullable=False)  # BACKTEST, AUDIT, PROMPT_EVOLUTION, etc.
    agent_role = Column(String(50), nullable=True)
    description = Column(Text, default="")
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "agent_role": self.agent_role,
            "description": self.description,
            "details": self.details,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CryptoStop(Base):
    __tablename__ = "crypto_stops"

    ticker = Column(String(20), primary_key=True)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    order_id = Column(String(100), nullable=True)
    status = Column(String(20), default="ACTIVE")  # ACTIVE, STOPPED, PROFIT_TAKEN
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "order_id": self.order_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ══════════════════════════════════════════════════════════════════
# DATABASE OPERATIONS
# ══════════════════════════════════════════════════════════════════

def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("database_initialized", url=DATABASE_URL, tables=len(Base.metadata.tables))


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


# ── Bug Operations ────────────────────────────────────────────────

def create_bug(
    id: str, title: str, severity: str = "MEDIUM",
    source: str = "", description: str = "",
) -> dict:
    """Create a new bug and return it as a dict."""
    with get_session() as s:
        bug = Bug(
            id=id, title=title, severity=severity,
            source=source, description=description,
        )
        s.add(bug)
        s.commit()
        s.refresh(bug)
        logger.info("bug_created_db", id=id[:8], severity=severity, title=title[:50])
        return bug.to_dict()


def get_bugs(status: Optional[str] = None) -> list[dict]:
    """Get all bugs, optionally filtered by status."""
    with get_session() as s:
        q = s.query(Bug)
        if status:
            q = q.filter(Bug.status == status)
        q = q.order_by(Bug.created_at.desc())
        return [b.to_dict() for b in q.all()]


def get_bug_summary() -> dict:
    """Get bug counts by status."""
    with get_session() as s:
        bugs = s.query(Bug).all()
        return {
            "total": len(bugs),
            "open": sum(1 for b in bugs if b.status == "OPEN"),
            "in_progress": sum(1 for b in bugs if b.status == "IN_PROGRESS"),
            "resolved": sum(1 for b in bugs if b.status == "RESOLVED"),
            "critical": sum(1 for b in bugs if b.severity == "CRITICAL"),
            "high": sum(1 for b in bugs if b.severity == "HIGH"),
        }


def update_bug(id: str, **kwargs) -> Optional[dict]:
    """Update a bug's fields."""
    with get_session() as s:
        bug = s.query(Bug).filter(Bug.id == id).first()
        if not bug:
            return None
        for k, v in kwargs.items():
            if hasattr(bug, k):
                setattr(bug, k, v)
        s.commit()
        s.refresh(bug)
        return bug.to_dict()


def get_open_bugs_sorted() -> list[dict]:
    """Get open bugs sorted by severity (CRITICAL first)."""
    priority = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    with get_session() as s:
        bugs = s.query(Bug).filter(Bug.status == "OPEN").all()
        bugs.sort(key=lambda b: priority.get(b.severity, 3))
        return [b.to_dict() for b in bugs]


# ── Feature Request Operations ────────────────────────────────────

def create_feature_request(
    id: str, title: str, description: str = "", analysis: str = "",
) -> dict:
    with get_session() as s:
        fr = FeatureRequest(
            id=id, title=title, description=description, analysis=analysis,
        )
        s.add(fr)
        s.commit()
        s.refresh(fr)
        return fr.to_dict()


def get_feature_requests() -> list[dict]:
    with get_session() as s:
        return [fr.to_dict() for fr in s.query(FeatureRequest).order_by(
            FeatureRequest.created_at.desc()
        ).all()]


# ── Trade Operations ──────────────────────────────────────────────

def create_trade(
    id: str, ticker: str, side: str, notional: float,
    division: str = "stocks", **kwargs,
) -> dict:
    with get_session() as s:
        trade = Trade(
            id=id, ticker=ticker, side=side,
            notional=notional, division=division, **kwargs,
        )
        s.add(trade)
        s.commit()
        s.refresh(trade)
        return trade.to_dict()


def get_recent_trades(limit: int = 50, division: Optional[str] = None) -> list[dict]:
    with get_session() as s:
        q = s.query(Trade)
        if division:
            q = q.filter(Trade.division == division)
        q = q.order_by(Trade.created_at.desc()).limit(limit)
        return [t.to_dict() for t in q.all()]


def update_trade(id: str, **kwargs) -> Optional[dict]:
    with get_session() as s:
        trade = s.query(Trade).filter(Trade.id == id).first()
        if not trade:
            return None
        for k, v in kwargs.items():
            if hasattr(trade, k):
                setattr(trade, k, v)
        s.commit()
        s.refresh(trade)
        return trade.to_dict()


# ── Agent Score Operations ────────────────────────────────────────

def upsert_agent_score(role: str, name: str, **kwargs) -> dict:
    with get_session() as s:
        agent = s.query(AgentScore).filter(AgentScore.role == role).first()
        if agent:
            for k, v in kwargs.items():
                if hasattr(agent, k) and v is not None:
                    setattr(agent, k, v)
        else:
            agent = AgentScore(role=role, name=name, **kwargs)
            s.add(agent)
        s.commit()
        s.refresh(agent)
        return agent.to_dict()


def get_agent_scores() -> list[dict]:
    with get_session() as s:
        return [a.to_dict() for a in s.query(AgentScore).all()]


# ── Evolution Event Operations ────────────────────────────────────

def create_evolution_event(
    id: str, event_type: str, description: str = "",
    agent_role: str = None, details: dict = None,
) -> dict:
    with get_session() as s:
        evt = EvolutionEvent(
            id=id, event_type=event_type, description=description,
            agent_role=agent_role, details=details,
        )
        s.add(evt)
        s.commit()
        s.refresh(evt)
        return evt.to_dict()


def get_evolution_events(limit: int = 50) -> list[dict]:
    with get_session() as s:
        return [e.to_dict() for e in s.query(EvolutionEvent).order_by(
            EvolutionEvent.created_at.desc()
        ).limit(limit).all()]


# ── Crypto Stop Operations ────────────────────────────────────────

def upsert_crypto_stop(ticker: str, entry_price: float, stop_loss: float,
                       take_profit: float, order_id: str = None) -> dict:
    with get_session() as s:
        stop = s.query(CryptoStop).filter(CryptoStop.ticker == ticker).first()
        if stop:
            stop.entry_price = entry_price
            stop.stop_loss = stop_loss
            stop.take_profit = take_profit
            stop.order_id = order_id
            stop.status = "ACTIVE"
        else:
            stop = CryptoStop(
                ticker=ticker, entry_price=entry_price,
                stop_loss=stop_loss, take_profit=take_profit, order_id=order_id,
            )
            s.add(stop)
        s.commit()
        s.refresh(stop)
        return stop.to_dict()


def get_active_crypto_stops() -> list[dict]:
    with get_session() as s:
        return [c.to_dict() for c in s.query(CryptoStop).filter(
            CryptoStop.status == "ACTIVE"
        ).all()]


# ── Sync: system_state ↔ DB ──────────────────────────────────────

def sync_state_from_db(system_state: dict):
    """Load DB data into system_state (called on startup)."""
    system_state["bugs"] = get_bugs()
    system_state["feature_requests"] = get_feature_requests()
    system_state["recent_trades"] = get_recent_trades()
    system_state["evolution_events"] = get_evolution_events()

    # Load agent scores into agents list
    scores = {a["role"]: a for a in get_agent_scores()}
    for agent in system_state.get("agents", []):
        role = agent.get("role", "")
        if role in scores:
            agent["trust_weight"] = scores[role].get("trust_weight", 1.0)
            agent["brier_score"] = scores[role].get("brier_score")

    logger.info(
        "state_synced_from_db",
        bugs=len(system_state["bugs"]),
        frs=len(system_state["feature_requests"]),
        trades=len(system_state["recent_trades"]),
    )


def migrate_json_to_db():
    """One-time migration: import data/state.json into the database."""
    import json
    json_file = os.path.join(DATA_DIR, "state.json")
    if not os.path.exists(json_file):
        return False

    try:
        with open(json_file) as f:
            data = json.load(f)

        migrated = 0

        # Migrate bugs
        for b in data.get("bugs", []):
            try:
                create_bug(
                    id=b["id"], title=b.get("title", ""),
                    severity=b.get("severity", "MEDIUM"),
                    source=b.get("source", ""),
                    description=b.get("description", ""),
                )
                migrated += 1
            except Exception:
                pass  # Already exists or invalid

        # Migrate FRs
        for fr in data.get("feature_requests", []):
            try:
                create_feature_request(
                    id=fr["id"], title=fr.get("title", ""),
                    description=fr.get("description", ""),
                    analysis=fr.get("analysis", ""),
                )
                migrated += 1
            except Exception:
                pass

        # Rename json to .migrated
        os.rename(json_file, json_file + ".migrated")
        logger.info("json_migrated_to_db", records=migrated)
        return True

    except Exception as e:
        logger.error("json_migration_failed", error=str(e))
        return False
