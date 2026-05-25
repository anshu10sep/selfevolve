# Agent Communication Protocol

Agents need a robust protocol to communicate with the central system and with each other.

## Communication Channels

### 1. Agent-to-Watchdog (Telemetry Push)
- **Protocol**: gRPC or UDP for high throughput, low latency.
- **Payload**: Minimal state packets. e.g., `{"agent_id": "007", "cpu_usage": "45%", "status": "ACTIVE"}`
- **Frequency**: Every 1-5 seconds.

### 2. Agent-to-Database (State Persistence)
- **Protocol**: HTTP/REST or Direct DB Connection (e.g., PostgreSQL driver).
- **Payload**: Large text blocks, code diffs, execution logs.
- **Frequency**: On job completion or significant milestone.

### 3. Agent-to-Agent (Peer Messaging)
- **Protocol**: Redis Pub/Sub or RabbitMQ.
- **Use Case**: A Coder Agent finishes writing a file and sends a message on the `code_ready` topic. A Reviewer Agent listening to that topic immediately picks it up.

## Dashboard Interaction
The dashboard visualizes the messaging bus. 
- The owner can see the volume of messages flowing through the pub/sub channels.
- In Level 3 Drilldown (Agent Details), the owner can view a live stream of the exact messages an agent is publishing or subscribing to.
