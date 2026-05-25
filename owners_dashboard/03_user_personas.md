# User Personas

The system is designed with specific user personas in mind, primarily focusing on the "Owner".

## 1. The System Owner (Primary Persona)
- **Role**: The ultimate decision-maker and overseer of the Jarvis ecosystem.
- **Needs**:
  - Wants a centralized dashboard to see everything without looking at raw logs.
  - Needs to monitor the Watchdog service.
  - Needs to see what the Jarvis core is currently optimizing or evolving.
  - Needs to track individual agents, what they are doing, and their PR status.
  - Wants control capabilities (e.g., manual override to "execute job" for an agent).
- **Interaction Model**: Visual, drill-down interactive UI.

## 2. The Developer / Operator (Secondary Persona)
- **Role**: Maintains the infrastructure underlying the Jarvis system.
- **Needs**:
  - Access to detailed error logs (secondary to the dashboard view).
  - Ability to scale the hardware or underlying Kubernetes cluster.
  - Monitors the Telemetry & Metrics engine for infrastructure health.
- **Interaction Model**: Command line interface, Grafana/Prometheus (though the Owner's Dashboard aggregates this).

## 3. The Autonomous Agent (System Persona)
- **Role**: The workers that execute tasks.
- **Needs**:
  - Clear task queues.
  - API access to external systems (GitHub, internal databases).
  - Ability to report status back to the Watchdog and State Storage.
