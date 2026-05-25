# Dashboard Drilldown Flow

The drilldown flow allows the owner to navigate from the macroscopic view of the system to the microscopic details of a single task execution.

## Level 1: The 10,000-Foot View
- **Visual**: A high-level topology graph.
- **Nodes**: Watchdog, Jarvis Core, Agent Cluster, Infrastructure.
- **Action**: Clicking on the "Agent Cluster" node transitions to Level 2.

## Level 2: Component Level (Agent Manager)
- **Visual**: A list or clustered graph of active, idle, and dead agents.
- **Data Displayed**: Total active agents, queue depth, resource utilization.
- **Action**: Clicking on a specific agent (e.g., `Agent-007`) transitions to Level 3.

## Level 3: Agent Details & Controls
- **Visual**: A dedicated dashboard for `Agent-007`.
- **Data Displayed**:
  - Current assigned task.
  - Historical success rate.
  - Logs (abstracted into readable events).
  - Associated PR links.
- **Controls**: Buttons to interact with the agent (e.g., "Force Execute", "Abort Task").
- **Action**: Clicking on a specific PR link transitions to Level 4.

## Level 4: Execution & External Integration Details
- **Visual**: Code diffs, pipeline statuses, and review comments.
- **Data Displayed**: Exact details of the PR uploaded to GitHub/GitLab, CI/CD run status for that PR.
- **Action**: Owner can approve the PR directly from the dashboard via API integration.
