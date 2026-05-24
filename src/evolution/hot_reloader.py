"""
Hot Reloader

Watches for code changes in the skills directories and agent modules.
When changes are detected, reloads the affected modules without
requiring a full system restart.
"""

from __future__ import annotations

import importlib
import os
import sys
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(component="hot_reloader")

SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class HotReloader:
    """Watches and reloads modified Python modules at runtime."""

    def __init__(self):
        self._watch_dirs: list[str] = [
            os.path.join(SRC_ROOT, "agents", "skills"),
            os.path.join(SRC_ROOT, "research"),
            os.path.join(SRC_ROOT, "integrations"),
        ]
        self._file_timestamps: dict[str, float] = {}
        self._reload_count = 0
        self._reload_history: list[dict] = []
        self._running = False

    def _scan_files(self) -> dict[str, float]:
        """Scan watched directories and return {filepath: mtime} dict."""
        files = {}
        for watch_dir in self._watch_dirs:
            if not os.path.exists(watch_dir):
                continue
            for root, dirs, filenames in os.walk(watch_dir):
                for fn in filenames:
                    if fn.endswith(".py") and not fn.startswith("__"):
                        filepath = os.path.join(root, fn)
                        files[filepath] = os.path.getmtime(filepath)
        return files

    def _filepath_to_module(self, filepath: str) -> Optional[str]:
        """Convert a file path to a Python module name."""
        try:
            rel = os.path.relpath(filepath, SRC_ROOT)
            module = rel.replace(os.sep, ".").replace(".py", "")
            return module
        except ValueError:
            return None

    async def check_and_reload(self) -> list[str]:
        """Check for modified files and reload them. Returns list of reloaded modules."""
        current = self._scan_files()
        reloaded = []

        for filepath, mtime in current.items():
            prev_mtime = self._file_timestamps.get(filepath)

            if prev_mtime is not None and mtime > prev_mtime:
                # File was modified
                module_name = self._filepath_to_module(filepath)
                if module_name and module_name in sys.modules:
                    try:
                        module = sys.modules[module_name]
                        importlib.reload(module)
                        reloaded.append(module_name)
                        self._reload_count += 1

                        record = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "module": module_name,
                            "file": filepath,
                            "success": True,
                        }
                        self._reload_history.append(record)

                        logger.info("module_reloaded", module=module_name, file=filepath)

                    except Exception as e:
                        logger.error("reload_failed", module=module_name, error=str(e))
                        self._reload_history.append({
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "module": module_name,
                            "file": filepath,
                            "success": False,
                            "error": str(e),
                        })

        # Update timestamps
        self._file_timestamps = current
        return reloaded

    async def watch_loop(self, interval_sec: int = 30):
        """
        Background loop that checks for changes every interval_sec.
        Run as a background task in main.py:
            asyncio.create_task(hot_reloader.watch_loop())
        """
        self._running = True
        # Initial scan to establish baseline
        self._file_timestamps = self._scan_files()
        logger.info("hot_reloader_started", watched_dirs=len(self._watch_dirs),
                     files_tracked=len(self._file_timestamps))

        while self._running:
            try:
                reloaded = await self.check_and_reload()
                if reloaded:
                    try:
                        from integrations.telegram_bot import send_alert
                        modules = ", ".join(f"`{m}`" for m in reloaded)
                        await send_alert(
                            f"🔄 *Hot Reload*\n\n"
                            f"Reloaded: {modules}\n"
                            f"Total reloads: {self._reload_count}"
                        )
                    except Exception:
                        pass

                await asyncio.sleep(interval_sec)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("hot_reloader_error", error=str(e))
                await asyncio.sleep(interval_sec)

        self._running = False

    def stop(self):
        """Stop the watch loop."""
        self._running = False

    def get_status(self) -> dict:
        """Get hot-reloader status for dashboard."""
        return {
            "running": self._running,
            "watched_dirs": len(self._watch_dirs),
            "files_tracked": len(self._file_timestamps),
            "total_reloads": self._reload_count,
            "recent_reloads": self._reload_history[-10:],
        }


# Module-level singleton
hot_reloader = HotReloader()
