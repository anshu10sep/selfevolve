# API Gateway

The API Gateway is the single point of entry for the Owner's Dashboard and any external integrations to interact with the Jarvis backend.

## Responsibilities

### 1. Routing
Routes REST and WebSocket traffic from the frontend dashboard to the appropriate microservice (e.g., `/api/watchdog/state` goes to the Watchdog service, `/api/jobs/execute` goes to the Agent Manager).

### 2. Authentication & Authorization
Validates the Owner's session token. Ensures that only authorized users can issue commands to the system.

### 3. Rate Limiting
Protects the internal services from being overwhelmed by too many requests (either from a buggy frontend or a malicious actor).

## Dashboard Control
The Gateway itself is monitored on the dashboard.
- The owner can see the total inbound traffic.
- If the system is under DDoS or experiencing a traffic spike, the owner can tighten rate limits dynamically via a toggle on the UI.
