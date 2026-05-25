# Resource Allocation and Scaling

To optimize costs and performance, the Jarvis ecosystem must intelligently manage its computing resources.

## Auto-Scaling Logic

The Agent Manager monitors the Task Queues.
- If `queue_coding` has 50 pending jobs and only 2 active agents, the Manager automatically requests more compute from the underlying infrastructure (Kubernetes Cluster Autoscaler).
- As the queue drains, the Manager scales down the infrastructure to save costs.

## Resource Quotas
Jarvis is constrained by owner-defined quotas to prevent runaway cloud bills.
- e.g., "Maximum 20 concurrent Coder Agents."
- e.g., "Maximum $100/day OpenAI API spend."

## Dashboard Controls
The "Resource Management" tab is crucial for the owner.
- Displays a live burn-rate graph (Cost per hour).
- Provides sliders to adjust the quotas dynamically.
- **Action**: `[Enable Aggressive Scaling]` (Overrides quotas temporarily to rush a critical feature).
