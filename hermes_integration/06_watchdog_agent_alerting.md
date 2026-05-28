# Watchdog and Alerting Automation

## Target Component
`src/evolution/watchdog.py` and `src/agents/watchdog_agent.py`

## Architecture Context
The Watchdog monitors the health of the system (logs, database stuck states, API ratelimits) and triggers alerts. Currently, it logs these issues and relies on a cron job. If the main daemon crashes, recovery is manual or relies on basic `systemd` restarts.

## Approaches

### Approach 1: Standard Webhook Alerts
The watchdog fires webhooks to PagerDuty or an external alerting service.
- **Pros**: Industry standard, highly reliable.
- **Cons**: Completely passive. Alerting services notify humans but do not attempt intelligent self-healing.

### Approach 2: Hermes Scheduled Automations with RPC Recovery
Deploy Hermes as an external sidecar. Use Hermes' "Scheduled Automations" (natural language cron) to periodically poll system health independently of our primary `APScheduler`. If Hermes detects a failure via its independent terminal access, it can execute automated Python RPC recovery scripts (e.g., clearing stuck Redis queues, reverting a bad PR, restarting the Docker container) before alerting the human.
- **Pros**: Active self-healing. Hermes acts as an intelligent SRE (Site Reliability Engineer) rather than a passive pager.
- **Cons**: Requires granting Hermes high-level privileges to manage the host system or containers.

## Recommendation: Approach 2 (Hermes Automations with RPC)
Integrating an intelligent SRE that operates entirely outside the primary event loop provides immense resilience. If the primary system locks up, Hermes can diagnose, attempt a fix via RPC, and provide a full post-mortem to the user via Discord/Telegram.
