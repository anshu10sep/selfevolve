# Agent Lifecycle

Understanding the lifecycle of an individual agent is crucial for debugging and monitoring via the dashboard.

## Lifecycle States

1. **PENDING**: The Agent Manager has received a request from Jarvis to create an agent, but resources (compute/memory) are currently being allocated.
2. **BOOTING**: The container is running, the LLM model weights are loading (if local), or API connections are being established.
3. **IDLE**: The agent is fully operational and is polling the Task Queue for work.
4. **ACTIVE**: The agent has pulled a job from the queue and is actively executing it.
5. **PAUSED**: Execution has been halted manually by the Owner via the dashboard, or automatically by the Watchdog due to a non-critical error.
6. **TERMINATING**: The agent is flushing its logs to the database and gracefully shutting down.
7. **DEAD**: An unnatural end to the agent (e.g., out-of-memory kill, crash).

## State Transitions on the Dashboard
The dashboard uses color-coding to represent these states visually:
- Gray: PENDING / BOOTING
- Blue: IDLE
- Green: ACTIVE
- Yellow: PAUSED
- Red: DEAD

Owners can click on any agent to view exactly how long it has spent in each state.
