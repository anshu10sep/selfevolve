# Event-Driven Architecture

To maintain a real-time, responsive dashboard without overloading databases, the system heavily utilizes an Event-Driven Architecture (EDA).

## The Event Bus
All significant state changes are broadcasted as Events to a central message broker (e.g., Apache Kafka or RabbitMQ).

## Event Examples
- `System.Initialized`
- `Agent.Spawned` (Payload: Agent ID, Type)
- `Job.Started` (Payload: Agent ID, Job ID)
- `PR.Drafted` (Payload: PR URL, Diff Summary)
- `Error.Critical` (Payload: Stack Trace)

## Dashboard WebSocket Streaming
The API Gateway subscribes to the Event Bus. When an event occurs, the Gateway pushes it down an open WebSocket connection to the Owner's Dashboard.
- This ensures the UI is updated instantly without the browser having to poll the server.
- Visual elements (like the 10,000-foot graph) react to these events (e.g., a node pulses green when `Job.Started` is received).
