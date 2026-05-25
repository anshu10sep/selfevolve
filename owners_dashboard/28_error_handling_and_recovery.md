# Error Handling and Recovery

A distributed system of autonomous agents will inevitably encounter errors. The architecture is designed to handle these gracefully and surface them to the dashboard.

## Error Categorization

1. **Transient Errors**: Network timeouts, GitHub API rate limits.
   - **Resolution**: Automated exponential backoff and retries handled by the Agent Manager.
2. **Logic Errors**: The agent wrote code that fails unit tests.
   - **Resolution**: The job is re-queued to a debugging agent.
3. **Fatal Errors**: Out of memory (OOM), kernel panics in the sandbox.
   - **Resolution**: The sandbox is killed, the job is marked failed, and an alert is sent to the Watchdog.

## Dashboard Surfacing
- Transient errors are hidden from the main view to reduce noise but are accessible in the raw logs.
- Logic errors are visualized in the PR Pipeline view (e.g., a red 'X' on the "Testing" phase).
- Fatal errors trigger a dashboard modal, prompting the owner to investigate or click `[Auto-Recover]`.
