# Jarvis Core Model

The Jarvis Core is the central intelligence of the architecture. It is an advanced LLM/Agentic construct that orchestrates the broader system.

## Responsibilities

### 1. High-Level Planning
When a complex goal is fed into the system, the Jarvis Core breaks it down into discrete, executable jobs.

### 2. Resource Allocation
Jarvis determines how many agents are needed to accomplish the jobs and what specific roles those agents should take (e.g., "Spawn 2 Code Writing Agents and 1 Review Agent").

### 3. Context Management
Jarvis maintains the "global context" of the codebase and project goals. It ensures that individual agents, which operate in isolated contexts, are given the right information to succeed.

## Architecture Intersections
- **Inbound**: Receives high-level commands from the Owner's Dashboard (or automated triggers).
- **Outbound**: Sends commands to the Agent Manager to spawn workers; sends task payloads to the Job Execution Engine.
- **Monitoring**: Continuously monitored by the Watchdog service to ensure logical consistency and uptime.

## Dashboard Representation
On the dashboard, Jarvis is represented as the central "Brain" node. Clicking on it reveals:
- Current global strategy being executed.
- Token usage and inference speed metrics.
- Active memory footprint and context window utilization.
