# Watchdog Service Design

The Watchdog Service is the omnipresent observer within the Jarvis ecosystem. Its primary role is to monitor everything and ensure the dashboard always has the latest state.

## Architecture of Watchdog

### 1. Data Ingestion
- **Pull Mechanism**: Actively polls health endpoints of Jarvis, Agent Manager, and critical databases.
- **Push Mechanism**: Exposes a telemetry API where agents push their state changes (e.g., "Starting Job", "Finished Job").

### 2. State Aggregation
- Maintains an in-memory graph of the system state.
- Correlates events (e.g., linking a high CPU alert to a specific agent executing a heavy job).

### 3. Broadcasting
- Pushes aggregated state to the Owner's Dashboard via WebSockets.
- Ensures the dashboard's interactive graph is updated in real-time with sub-second latency.

## Key Responsibilities
- **Liveness Tracking**: Detecting if an agent has frozen or died.
- **Anomaly Detection**: Identifying if the Jarvis core model is looping or degrading in performance.
- **Security Auditing**: Ensuring agents do not access unauthorized repositories.

## Interfacing with the Dashboard
The dashboard relies on the Watchdog as its single source of truth for the system's operational status. The Watchdog does not control the system; it only observes and reports.
