# Task Queue and Job Routing

The core mechanism for distributing work among agents is the Task Queue.

## Architecture

### The Central Queue (e.g., Redis / RabbitMQ)
- Maintains separate queues based on task type (e.g., `queue_coding`, `queue_reviewing`, `queue_testing`).
- Jobs are pushed into these queues by the Jarvis Core Model or Planner Agents.

### Job Structure
A standard Job payload contains:
```json
{
  "job_id": "job-1024",
  "type": "code_generation",
  "priority": "high",
  "context": {
    "file_path": "/src/auth.py",
    "objective": "Implement JWT validation"
  },
  "timeout_seconds": 600
}
```

### Job Routing
- **Pull-Based**: Idle agents subscribe to the queue matching their Role. When they become IDLE, they pull the next available job.
- **Priority Routing**: High priority jobs jump to the front of the queue. If a critical bug is detected, Jarvis can inject a `critical` priority job that will be picked up immediately.

## Dashboard Visibility
The Owner's Dashboard features a dedicated "Queues" panel.
- Shows total pending jobs per queue.
- Allows the owner to manually reorder jobs, delete jobs, or inject new jobs directly from the UI.
