# Jarvis Self-Evolution Cycle

The Self-Evolution Cycle is what sets Jarvis apart from static orchestration systems. It is the process by which the Core Model improves its own code, prompts, or policies based on past performance.

## The Evolution Loop

1. **Metrics Gathering**: Watchdog continuously pushes metrics (e.g., job completion rate, code error rates) into the Telemetry database.
2. **Periodic Assessment**: On a scheduled cron job (or triggered by a specific event), Jarvis runs an "Evolution Assessment" over the recent historical data.
3. **Hypothesis Generation**: If Jarvis identifies a bottleneck (e.g., "Review agents are taking too long and failing to catch syntax errors"), it generates a hypothesis ("Updating the review agent's system prompt to enforce AST checking will improve speed and accuracy").
4. **Experimentation**: Jarvis asks the Agent Manager to spawn a specialized "Dev Agent" to implement this change on a branch.
5. **Deployment & A/B Testing**: The new agent variant is deployed alongside the old one. If telemetry shows improvement, the change is merged into the `main` branch.

## Dashboard Visibility
The Owner's Dashboard displays active Evolution Cycles.
- A dedicated panel shows "Current Hypotheses Being Tested."
- The owner can click `[Approve Evolution]` or `[Reject Evolution]` to manually control the self-improvement process if they don't want it running fully autonomously.
