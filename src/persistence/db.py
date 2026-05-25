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


class PredictionRecord(Base):
    """Records every agent prediction for Brier score calculation.

    Each time an analyst agent produces a ConvictionScore for a trade,
    we store the predicted probability and later fill in the actual
    outcome (1 = profitable, 0 = loss) when the trade closes.
    """
    __tablename__ = "prediction_records"

    id = Column(String(36), primary_key=True)
    agent_role = Column(String(50), nullable=False)
    trade_id = Column(String(36), nullable=False)
    ticker = Column(String(20), nullable=False)
    predicted_probability = Column(Float, nullable=False)  # 0.0–1.0
    confidence = Column(Float, nullable=False)             # 0.0–1.0
    actual_outcome = Column(Integer, nullable=True)        # 0 or 1, filled on trade close
    prompt_version = Column(Integer, default=1)            # which prompt version made this
    is_shadow = Column(Boolean, default=False)             # True if from shadow crew
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_predictions_agent_role", "agent_role"),
        Index("ix_predictions_trade_id", "trade_id"),
        Index("ix_predictions_is_shadow", "is_shadow"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_role": self.agent_role,
            "trade_id": self.trade_id,
            "ticker": self.ticker,
            "predicted_probability": self.predicted_probability,
            "confidence": self.confidence,
            "actual_outcome": self.actual_outcome,
            "prompt_version": self.prompt_version,
            "is_shadow": self.is_shadow,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class PromptVersion(Base):
    """Tracks prompt evolution history for each agent.

    Stores every Strategic_Nuance version so we can A/B test
    candidate prompts against production and roll back if needed.
    """
    __tablename__ = "prompt_versions"

    id = Column(String(36), primary_key=True)
    agent_role = Column(String(50), nullable=False)
    version_number = Column(Integer, nullable=False)
    prompt_text = Column(Text, nullable=False)          # The Strategic_Nuance content
    is_active = Column(Boolean, default=False)
    change_description = Column(Text, default="")
    brier_before = Column(Float, nullable=True)
    brier_after = Column(Float, nullable=True)
    trade_count = Column(Integer, default=0)
    p_value = Column(Float, nullable=True)
    ab_test_result = Column(String(20), default="PENDING")  # PENDING, PROMOTED, ROLLED_BACK, INCONCLUSIVE
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_prompt_versions_agent_role", "agent_role"),
        Index("ix_prompt_versions_active", "is_active"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_role": self.agent_role,
            "version_number": self.version_number,
            "prompt_text": self.prompt_text,
            "is_active": self.is_active,
            "change_description": self.change_description,
            "brier_before": self.brier_before,
            "brier_after": self.brier_after,
            "trade_count": self.trade_count,
            "p_value": self.p_value,
            "ab_test_result": self.ab_test_result,
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


def create_bug_dedup(
    title: str, severity: str = "MEDIUM",
    source: str = "", description: str = "",
) -> Optional[dict]:
    """Create a bug only if no bug with the same title already exists.

    This is the preferred entry point for ALL automated bug filing.
    Returns the new bug dict if created, or None if a duplicate exists.
    """
    import uuid
    with get_session() as s:
        existing = s.query(Bug).filter(Bug.title == title).first()
        if existing:
            logger.debug("bug_dedup_skipped", title=title[:50],
                         existing_id=existing.id[:8], existing_status=existing.status)
            return None
        bug = Bug(
            id=str(uuid.uuid4()), title=title, severity=severity,
            source=source, description=description,
        )
        s.add(bug)
        s.commit()
        s.refresh(bug)
        logger.info("bug_created_dedup", id=bug.id[:8], severity=severity, title=title[:50])
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


def get_stuck_bugs(stuck_minutes: int = 60) -> list[dict]:
    """Get IN_PROGRESS bugs that have a worker_error or have been stuck too long.

    A bug is considered 'stuck' if:
    - Status is IN_PROGRESS AND has a worker_error set, OR
    - Status is IN_PROGRESS AND started_at is older than stuck_minutes ago
    """
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stuck_minutes)
    with get_session() as s:
        bugs = s.query(Bug).filter(
            Bug.status == "IN_PROGRESS",
        ).all()
        stuck = []
        for b in bugs:
            has_error = bool(b.worker_error)
            is_stale = b.started_at and b.started_at.replace(
                tzinfo=timezone.utc if b.started_at.tzinfo is None else b.started_at.tzinfo
            ) < cutoff
            if has_error or is_stale:
                stuck.append(b.to_dict())
        return stuck


def reset_stuck_bugs(stuck_minutes: int = 60) -> int:
    """Reset stuck IN_PROGRESS bugs back to OPEN so bug worker retries them.

    Returns the number of bugs reset.
    """
    stuck = get_stuck_bugs(stuck_minutes=stuck_minutes)
    count = 0
    for bug_dict in stuck:
        update_bug(
            bug_dict["id"],
            status="OPEN",
            worker_error=None,
            started_at=None,
        )
        count += 1
        logger.info("bug_reset_to_open", bug_id=bug_dict["id"][:8],
                     title=bug_dict["title"][:50], reason="stuck_in_progress")
    return count



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


# ── Prediction Record Operations ──────────────────────────────────

def create_prediction(
    id: str, agent_role: str, trade_id: str, ticker: str,
    predicted_probability: float, confidence: float,
    prompt_version: int = 1, is_shadow: bool = False,
) -> dict:
    """Record an agent's prediction for later Brier scoring."""
    with get_session() as s:
        rec = PredictionRecord(
            id=id, agent_role=agent_role, trade_id=trade_id,
            ticker=ticker, predicted_probability=predicted_probability,
            confidence=confidence, prompt_version=prompt_version,
            is_shadow=is_shadow,
        )
        s.add(rec)
        s.commit()
        s.refresh(rec)
        logger.info(
            "prediction_recorded",
            agent=agent_role, trade=trade_id[:8], ticker=ticker,
            prob=f"{predicted_probability:.2f}", shadow=is_shadow,
        )
        return rec.to_dict()


def update_prediction_outcome(trade_id: str, actual_outcome: int) -> int:
    """Set the actual outcome (0=loss, 1=win) for all predictions on a trade.

    Called when a trade closes. Returns the number of predictions updated.
    """
    with get_session() as s:
        preds = s.query(PredictionRecord).filter(
            PredictionRecord.trade_id == trade_id,
            PredictionRecord.actual_outcome.is_(None),
        ).all()
        count = 0
        for p in preds:
            p.actual_outcome = actual_outcome
            p.resolved_at = datetime.now(timezone.utc)
            count += 1
        s.commit()
        if count:
            logger.info("prediction_outcomes_set", trade=trade_id[:8], count=count, outcome=actual_outcome)
        return count


def get_predictions_for_agent(
    agent_role: str, resolved_only: bool = True,
    is_shadow: bool = False, limit: int = 50,
) -> list[dict]:
    """Get predictions for an agent, optionally filtered by resolved/shadow status."""
    with get_session() as s:
        q = s.query(PredictionRecord).filter(
            PredictionRecord.agent_role == agent_role,
            PredictionRecord.is_shadow == is_shadow,
        )
        if resolved_only:
            q = q.filter(PredictionRecord.actual_outcome.isnot(None))
        q = q.order_by(PredictionRecord.created_at.desc()).limit(limit)
        return [p.to_dict() for p in q.all()]


def get_predictions_for_prompt_version(
    agent_role: str, prompt_version: int, resolved_only: bool = True,
) -> list[dict]:
    """Get predictions made by a specific prompt version (for A/B testing)."""
    with get_session() as s:
        q = s.query(PredictionRecord).filter(
            PredictionRecord.agent_role == agent_role,
            PredictionRecord.prompt_version == prompt_version,
        )
        if resolved_only:
            q = q.filter(PredictionRecord.actual_outcome.isnot(None))
        q = q.order_by(PredictionRecord.created_at.desc())
        return [p.to_dict() for p in q.all()]


def get_unresolved_trade_ids() -> list[dict]:
    """Get unique trade_ids with unresolved predictions (actual_outcome IS NULL).

    Returns list of dicts: {trade_id, ticker, created_at}
    Used by the PredictionResolver to know which trades still need outcomes.
    """
    with get_session() as s:
        from sqlalchemy import func, distinct
        rows = (
            s.query(
                PredictionRecord.trade_id,
                PredictionRecord.ticker,
                func.min(PredictionRecord.created_at).label("created_at"),
            )
            .filter(PredictionRecord.actual_outcome.is_(None))
            .group_by(PredictionRecord.trade_id, PredictionRecord.ticker)
            .order_by(func.min(PredictionRecord.created_at).asc())
            .all()
        )
        return [
            {
                "trade_id": r.trade_id,
                "ticker": r.ticker,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def update_crypto_stop_status(ticker: str, status: str) -> Optional[dict]:
    """Update a crypto stop's status (ACTIVE → STOPPED or PROFIT_TAKEN)."""
    with get_session() as s:
        stop = s.query(CryptoStop).filter(CryptoStop.ticker == ticker).first()
        if not stop:
            return None
        stop.status = status
        s.commit()
        s.refresh(stop)
        return stop.to_dict()


# ── Prompt Version Operations ─────────────────────────────────────

def create_prompt_version(
    id: str, agent_role: str, version_number: int,
    prompt_text: str, change_description: str = "",
    brier_before: float = None, is_active: bool = False,
) -> dict:
    """Create a new prompt version (candidate for A/B testing)."""
    with get_session() as s:
        pv = PromptVersion(
            id=id, agent_role=agent_role, version_number=version_number,
            prompt_text=prompt_text, change_description=change_description,
            brier_before=brier_before, is_active=is_active,
        )
        s.add(pv)
        s.commit()
        s.refresh(pv)
        logger.info(
            "prompt_version_created",
            agent=agent_role, version=version_number,
            active=is_active,
        )
        return pv.to_dict()


def get_active_prompt(agent_role: str) -> Optional[dict]:
    """Get the currently active Strategic_Nuance for an agent."""
    with get_session() as s:
        pv = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
            PromptVersion.is_active == True,
        ).order_by(PromptVersion.version_number.desc()).first()
        return pv.to_dict() if pv else None


def get_pending_prompt_versions(agent_role: str) -> list[dict]:
    """Get prompt versions that are still being A/B tested."""
    with get_session() as s:
        pvs = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
            PromptVersion.ab_test_result == "PENDING",
        ).order_by(PromptVersion.created_at.desc()).all()
        return [pv.to_dict() for pv in pvs]


def promote_prompt_version(agent_role: str, version_number: int, p_value: float = None) -> Optional[dict]:
    """Promote a candidate prompt to active and deactivate the old one."""
    with get_session() as s:
        # Deactivate current active
        current = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
            PromptVersion.is_active == True,
        ).all()
        for pv in current:
            pv.is_active = False

        # Activate new version
        new = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
            PromptVersion.version_number == version_number,
        ).first()
        if not new:
            return None
        new.is_active = True
        new.ab_test_result = "PROMOTED"
        if p_value is not None:
            new.p_value = p_value
        s.commit()
        s.refresh(new)
        logger.info(
            "prompt_promoted",
            agent=agent_role, version=version_number,
            p_value=p_value,
        )
        return new.to_dict()


def discard_prompt_version(agent_role: str, version_number: int, p_value: float = None) -> Optional[dict]:
    """Mark a candidate prompt as rolled back / discarded."""
    with get_session() as s:
        pv = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
            PromptVersion.version_number == version_number,
        ).first()
        if not pv:
            return None
        pv.ab_test_result = "ROLLED_BACK"
        if p_value is not None:
            pv.p_value = p_value
        s.commit()
        s.refresh(pv)
        logger.info("prompt_discarded", agent=agent_role, version=version_number)
        return pv.to_dict()


def get_latest_prompt_version_number(agent_role: str) -> int:
    """Get the highest version number for an agent (0 if none exist)."""
    with get_session() as s:
        pv = s.query(PromptVersion).filter(
            PromptVersion.agent_role == agent_role,
        ).order_by(PromptVersion.version_number.desc()).first()
        return pv.version_number if pv else 0


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

    # Restore all-time activity counters into the activity tracker
    try:
        from core.activity_tracker import tracker
        tracker.load_from_dict(scores)
    except Exception as e:
        logger.warning("activity_tracker_restore_skipped", error=str(e))

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
