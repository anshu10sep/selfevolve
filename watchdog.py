#!/usr/bin/env python3
"""
Jarvis Health Watchdog — External oversight script.

Runs every 30 minutes via cron. Checks:
  1. Is the jarvis service running?
  2. Are bugs being processed?
  3. Are PRs being created and merged?
  4. Is the evolution engine working?
  5. Are there any stuck issues?

If problems are found, it writes a diagnostic report and can restart the service.
"""

import os
import sys
import json
import subprocess
import sqlite3
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__)))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
LOG_DIR = os.path.join(REPO_ROOT, "logs")
DB_PATH = os.path.join(REPO_ROOT, "data", "jarvis.db")
REPORT_PATH = os.path.join(LOG_DIR, "watchdog_report.log")


def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line)
    with open(REPORT_PATH, "a") as f:
        f.write(line + "\n")


def check_service_running():
    """Check if jarvis systemd service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "jarvis"],
            capture_output=True, text=True, timeout=5,
        )
        status = result.stdout.strip()
        if status == "active":
            pid_result = subprocess.run(
                ["systemctl", "show", "jarvis", "--property=MainPID"],
                capture_output=True, text=True, timeout=5,
            )
            pid = pid_result.stdout.strip().split("=")[-1]
            return True, f"active (PID {pid})"
        return False, f"status: {status}"
    except Exception as e:
        return False, str(e)


def check_recent_logs(minutes=35):
    """Check if jarvis has been logging recently."""
    log_file = os.path.join(LOG_DIR, "jarvis.log")
    if not os.path.exists(log_file):
        return False, "jarvis.log not found"

    try:
        mtime = os.path.getmtime(log_file)
        age_seconds = (datetime.now().timestamp() - mtime)
        if age_seconds > minutes * 60:
            return False, f"Log file stale ({age_seconds/60:.0f}min old)"
        return True, f"Log updated {age_seconds:.0f}s ago"
    except Exception as e:
        return False, str(e)


def check_recent_errors():
    """Check for recent errors in the last 35 minutes."""
    log_file = os.path.join(LOG_DIR, "jarvis.log")
    if not os.path.exists(log_file):
        return 0, []

    errors = []
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=35)
    try:
        with open(log_file) as f:
            for line in f:
                if '"level": "error"' in line:
                    try:
                        entry = json.loads(line.strip())
                        ts = entry.get("timestamp", "")
                        if ts:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt > cutoff:
                                errors.append({
                                    "component": entry.get("component", "?"),
                                    "event": entry.get("event", "?"),
                                    "error": entry.get("error", "?")[:100],
                                })
                    except (json.JSONDecodeError, ValueError):
                        pass
    except Exception:
        pass
    return len(errors), errors[-5:]


def check_bug_pipeline():
    """Check bug database for pipeline health."""
    if not os.path.exists(DB_PATH):
        return {"error": "DB not found"}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Count bugs by status
        c.execute("SELECT status, COUNT(*) as cnt FROM bugs GROUP BY status")
        status_counts = {row["status"]: row["cnt"] for row in c.fetchall()}

        # Count bugs resolved in last 2 hours
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        c.execute("SELECT COUNT(*) FROM bugs WHERE status='RESOLVED' AND resolved_at > ?", (cutoff,))
        recently_resolved = c.fetchone()[0]

        # Count stuck bugs (OPEN > 1 hour)
        stuck_cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        c.execute("SELECT COUNT(*) FROM bugs WHERE status='OPEN' AND created_at < ?", (stuck_cutoff,))
        stuck = c.fetchone()[0]

        conn.close()

        return {
            "total": sum(status_counts.values()),
            "open": status_counts.get("OPEN", 0),
            "in_progress": status_counts.get("IN_PROGRESS", 0),
            "resolved": status_counts.get("RESOLVED", 0),
            "recently_resolved_2h": recently_resolved,
            "stuck_over_1h": stuck,
        }
    except Exception as e:
        return {"error": str(e)}


def check_github_prs():
    """Check GitHub for open PRs."""
    try:
        sys.path.insert(0, SRC_ROOT)
        from config.settings import get_settings
        settings = get_settings()
        pat = settings.github_pat
        repo = settings.github_repo

        import urllib.request
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/pulls?state=open",
            headers={
                "Authorization": f"token {pat}",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            prs = json.loads(resp.read())

        open_prs = [{"number": pr["number"], "title": pr["title"][:60]} for pr in prs]
        return {"open_count": len(open_prs), "prs": open_prs}
    except Exception as e:
        return {"error": str(e)}


def check_evolution_engine():
    """Check if evolution engine has been running."""
    log_file = os.path.join(LOG_DIR, "jarvis.log")
    if not os.path.exists(log_file):
        return {"running": False}

    last_check = None
    merge_count = 0
    try:
        with open(log_file) as f:
            for line in f:
                if "evolution_checking_prs" in line or "evolution_cycle_no_merges" in line:
                    try:
                        entry = json.loads(line.strip())
                        last_check = entry.get("timestamp", "")
                    except json.JSONDecodeError:
                        pass
                if "pr_merged" in line or "auto_merging" in line:
                    merge_count += 1
    except Exception:
        pass

    return {
        "last_check": last_check,
        "total_merges": merge_count,
    }


def restart_service():
    """Force restart the jarvis service."""
    log("🔄 RESTARTING JARVIS SERVICE")
    try:
        result = subprocess.run(
            ["systemctl", "show", "jarvis", "--property=MainPID"],
            capture_output=True, text=True, timeout=5,
        )
        pid = result.stdout.strip().split("=")[-1]
        if pid and pid != "0":
            subprocess.run(["kill", "-9", pid], timeout=5)
            log(f"   Sent SIGKILL to PID {pid}")
            import time
            time.sleep(15)

            # Verify restart
            ok, status = check_service_running()
            log(f"   After restart: {status}")
            return ok
    except Exception as e:
        log(f"   Restart failed: {e}")
    return False


def run_watchdog():
    """Main watchdog check."""
    log("=" * 60)
    log("🔍 JARVIS WATCHDOG CHECK")
    log("=" * 60)

    issues = []
    actions = []

    # 1. Service health
    running, status = check_service_running()
    log(f"  Service: {'✅' if running else '❌'} {status}")
    if not running:
        issues.append("Service not running")
        actions.append("RESTART")

    # 2. Recent logs
    logging_ok, log_status = check_recent_logs()
    log(f"  Logging: {'✅' if logging_ok else '❌'} {log_status}")
    if not logging_ok:
        issues.append(f"Logging stale: {log_status}")

    # 3. Recent errors
    error_count, recent_errors = check_recent_errors()
    log(f"  Errors (last 35min): {'✅' if error_count < 5 else '⚠️'} {error_count}")
    for e in recent_errors:
        log(f"    - [{e['component']}] {e['event']}: {e['error'][:80]}")

    # 4. Bug pipeline
    pipeline = check_bug_pipeline()
    if "error" not in pipeline:
        stuck = pipeline.get("stuck_over_1h", 0)
        log(f"  Bugs: Open={pipeline['open']} InProgress={pipeline['in_progress']} "
            f"Resolved={pipeline['resolved']} RecentlyResolved={pipeline['recently_resolved_2h']} "
            f"Stuck={stuck}")
        if stuck > 10:
            issues.append(f"{stuck} bugs stuck > 1 hour")
    else:
        log(f"  Bugs: ❌ {pipeline['error']}")

    # 5. GitHub PRs
    gh = check_github_prs()
    if "error" not in gh:
        log(f"  GitHub: {gh['open_count']} open PRs")
        for pr in gh.get("prs", [])[:5]:
            log(f"    - PR #{pr['number']}: {pr['title']}")
        if gh["open_count"] > 10:
            issues.append(f"{gh['open_count']} unmerged PRs piling up")
    else:
        log(f"  GitHub: ❌ {gh['error']}")

    # 6. Evolution engine
    evo = check_evolution_engine()
    log(f"  Evolution: Last check={evo.get('last_check', 'never')} "
        f"Merges={evo.get('total_merges', 0)}")
    if not evo.get("last_check"):
        issues.append("Evolution engine has never checked PRs")

    # Summary
    log("")
    if issues:
        log(f"⚠️  ISSUES FOUND: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            log(f"  {i}. {issue}")

        if "RESTART" in actions:
            restart_service()
    else:
        log("✅ ALL SYSTEMS HEALTHY")

    log("")
    return len(issues)


if __name__ == "__main__":
    run_watchdog()
