# Watchdog Health Checks

The Watchdog service relies on a robust set of health checks to determine the status of the ecosystem.

## Types of Health Checks

### 1. Liveness Probes
- **Target**: All services (Jarvis Core, Agent Manager, API Gateway).
- **Mechanism**: Simple HTTP `GET /health` or gRPC ping.
- **Purpose**: Answers "Is the process running and able to accept connections?"

### 2. Readiness Probes
- **Target**: Agent Workers.
- **Mechanism**: Checks if the agent has loaded its model weights into VRAM and connected to the task queue.
- **Purpose**: Answers "Is the agent ready to accept a new job?"

### 3. Semantic / Behavioral Checks
- **Target**: Jarvis Core.
- **Mechanism**: The Watchdog occasionally injects a dummy prompt into Jarvis and measures the response time and coherence.
- **Purpose**: Ensures the AI model hasn't degraded into generating gibberish (model collapse).

### 4. Dependency Checks
- **Target**: External APIs (GitHub API, Database).
- **Mechanism**: Validating API tokens and checking external service status pages.
- **Purpose**: Ensures agents won't fail due to external outages.

## Dashboard Integration
Health check results are translated into node colors on the Dashboard's interactive UI:
- **Green**: All checks passing.
- **Yellow**: Degraded performance (e.g., high latency).
- **Red**: Liveness or critical dependency failure.
