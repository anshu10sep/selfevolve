# Watchdog Alerting Rules

When the Watchdog service detects anomalies during its health checks, it triggers alerts based on predefined rules. These alerts are visualized prominently on the Owner's Dashboard.

## Alert Severity Levels

1. **INFO**: Routine events. (e.g., "Agent-001 spawned successfully").
2. **WARNING**: Non-critical issues that require attention. (e.g., "GitHub API rate limit at 80%").
3. **CRITICAL**: System-breaking issues. (e.g., "Jarvis Core offline", "Database connection lost").

## Sample Alerting Rules

### Rule 1: Agent Zombie Detection
- **Condition**: Agent heartbeat missing for > 30 seconds AND agent state is 'ACTIVE'.
- **Action**: Generate WARNING alert. Trigger Agent Manager to attempt a restart.

### Rule 2: Excessive Error Rate
- **Condition**: An agent fails > 3 consecutive jobs.
- **Action**: Generate CRITICAL alert. Isolate the agent and pause its queue to prevent further damage.

### Rule 3: Resource Exhaustion
- **Condition**: Overall system memory usage > 90%.
- **Action**: Generate CRITICAL alert. Prevent Agent Manager from spinning up new agents until resources free up.

## Dashboard Visualization
- Alerts appear in the Live Activity Feed.
- CRITICAL alerts trigger a system-wide modal on the dashboard, requiring the owner to acknowledge and take action (e.g., clicking "Approve Agent Purge").
