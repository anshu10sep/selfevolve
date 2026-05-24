"""
State Persistence

Saves system_state to a JSON file on disk so it survives Jarvis restarts.
Loads on startup, auto-saves every 60 seconds and on every mutation.

Storage: ~/self-evolving/data/state.json
"""

from __future__ import annotations

import json
import os
import asyncio
import shutil
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(component="persistence")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
BACKUP_FILE = os.path.join(DATA_DIR, "state.backup.json")

# Keys that get persisted across restarts
PERSISTENT_KEYS = [
    "bugs",
    "feature_requests",
    "recent_trades",
    "evolution_events",
    "daily_progress",
    "roadmap",
    "hitl_queue",
    "crypto_stops",
    "system_audit",
]

# Agent fields that persist (trust scores, brier, activity counters)
AGENT_PERSISTENT_FIELDS = [
    "trust_weight", "brier_score", "tasks_today", "cost_today",
]


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def save_state(system_state: dict[str, Any]) -> bool:
    """Save persistent parts of system_state to disk."""
    try:
        _ensure_dir()

        # Build the data to persist
        data: dict[str, Any] = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }

        # Save persistent keys
        for key in PERSISTENT_KEYS:
            if key in system_state:
                data[key] = system_state[key]

        # Save agent trust/brier scores keyed by role (stable across restarts)
        agent_data = {}
        for agent in system_state.get("agents", []):
            role = agent.get("role", "")
            if role:
                agent_data[role] = {
                    f: agent.get(f) for f in AGENT_PERSISTENT_FIELDS
                }
        data["agent_scores"] = agent_data

        # Atomic write: write to temp file, then rename
        tmp_file = STATE_FILE + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

        # Backup current file before overwriting
        if os.path.exists(STATE_FILE):
            shutil.copy2(STATE_FILE, BACKUP_FILE)

        os.rename(tmp_file, STATE_FILE)

        logger.debug(
            "state_saved",
            bugs=len(data.get("bugs", [])),
            trades=len(data.get("recent_trades", [])),
            frs=len(data.get("feature_requests", [])),
        )
        return True

    except Exception as e:
        logger.error("state_save_failed", error=str(e))
        return False


def load_state(system_state: dict[str, Any]) -> bool:
    """Load persisted state from disk into system_state."""
    try:
        if not os.path.exists(STATE_FILE):
            logger.info("no_persisted_state", message="Starting fresh")
            return False

        with open(STATE_FILE, "r") as f:
            data = json.load(f)

        loaded_keys = []

        # Restore persistent keys
        for key in PERSISTENT_KEYS:
            if key in data and data[key]:
                system_state[key] = data[key]
                loaded_keys.append(f"{key}({len(data[key]) if isinstance(data[key], list) else '✓'})")

        # Restore agent scores
        agent_scores = data.get("agent_scores", {})
        if agent_scores:
            for agent in system_state.get("agents", []):
                role = agent.get("role", "")
                if role in agent_scores:
                    for field, value in agent_scores[role].items():
                        if value is not None:
                            agent[field] = value
            loaded_keys.append(f"agents({len(agent_scores)})")

        # Restore feature_requests if present
        if "feature_requests" in data:
            system_state["feature_requests"] = data["feature_requests"]

        saved_at = data.get("saved_at", "unknown")
        logger.info(
            "state_loaded",
            saved_at=saved_at,
            keys=", ".join(loaded_keys),
        )
        return True

    except json.JSONDecodeError as e:
        logger.error("state_load_corrupt", error=str(e))
        # Try backup
        if os.path.exists(BACKUP_FILE):
            logger.info("trying_backup_state")
            try:
                shutil.copy2(BACKUP_FILE, STATE_FILE)
                return load_state(system_state)
            except Exception:
                pass
        return False
    except Exception as e:
        logger.error("state_load_failed", error=str(e))
        return False


async def auto_save_loop(system_state: dict[str, Any], interval_sec: int = 60):
    """Background loop that auto-saves state every N seconds."""
    while True:
        try:
            await asyncio.sleep(interval_sec)
            save_state(system_state)
        except asyncio.CancelledError:
            # Final save on shutdown
            save_state(system_state)
            break
        except Exception as e:
            logger.error("auto_save_error", error=str(e))
            await asyncio.sleep(interval_sec)


def save_now(system_state: dict[str, Any]):
    """Convenience: save immediately (call after mutations like bug creation)."""
    save_state(system_state)
