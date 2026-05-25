# Agent Manager Service

The Agent Manager acts as the bridge between the Jarvis Core Model's high-level intent and the physical execution of agents.

## Responsibilities

### 1. Agent Provisioning
When Jarvis decides it needs an agent, it sends a payload to the Agent Manager:
`{"type": "coder", "count": 2, "context": "build login page"}`
The Manager translates this into infrastructure commands (e.g., Kubernetes API calls or Docker run commands) to spin up the actual isolated containers.

### 2. State Tracking
The Manager maintains a registry of all active agents. It tracks:
- Agent ID
- Container / Process ID
- Current assigned Job ID
- Start Time & Uptime

### 3. Graceful Termination
When an agent finishes its task, or if Jarvis decides it is no longer needed, the Agent Manager safely shuts down the agent, ensuring any in-memory state or logs are flushed to the State Storage database before termination.

## Dashboard Drilldown
On the Owner's Dashboard, the Agent Manager is visible as a critical node.
- Hovering over the Agent Manager shows the current scale (e.g., "15 Active Agents, 2 Pending, 0 Dead").
- Clicking on it opens a table view of the Agent Registry.
