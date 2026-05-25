# Dashboard Control Actions

The Owner's Dashboard is not just a passive monitoring tool; it is an active command center.

## Global Actions
- **`[System Halt]`**: Instantly pauses all Agent Managers. Running sandboxes are frozen. Used in emergencies.
- **`[Trigger Jarvis Evolution]`**: Forces the Jarvis Core to run a self-assessment and evolution cycle immediately, overriding the cron schedule.

## Agent-Level Actions
When drilling down into a specific agent, the owner has granular controls:
- **`[Execute Job]`**: Manually assign a specific job ID to an idle agent, bypassing the queue.
- **`[Pause Agent]`**: Stops the agent from pulling new jobs. Current job continues until completion.
- **`[Kill Agent]`**: Gracefully terminates the agent and returns its job to the queue.
- **`[Force Purge]`**: Violently kills the agent's container. The job is marked as FAILED.

## Job-Level Actions
- **`[Re-queue Job]`**: Takes a job that failed or stalled and puts it back in the queue.
- **`[Edit Job Payload]`**: Allows the owner to manually alter the JSON payload of a queued job (e.g., adding more context before an agent picks it up).

## Security
All control actions are logged in an immutable audit trail, visible in the "Audit Logs" section of the dashboard, ensuring complete accountability.
