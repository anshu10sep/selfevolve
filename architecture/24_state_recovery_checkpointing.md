# State Recovery and Checkpointing

## System Resilience
In a fully autonomous financial system, server process crashes, network timeouts, or API rate limits are inevitable. The architecture must handle these gracefully without executing duplicate transactions or losing portfolio context.

## LangGraph Persistent Checkpointing
- **Thread-Level State**: LangGraph inherently treats workflows as state graphs. By attaching a persistent database (e.g., PostgreSQL or SQLite) to the graph compiler, the system checkpoints its exact state after every single node transition.
- **Crash Recovery**: If the system goes offline immediately after the Bull Agent completes but before the Bear Agent starts, the restart sequence simply reloads the state thread and resumes exactly at the Bear Agent node.

## Transactional Boundaries
- Order execution calls to the Alpaca API must be treated as idempotent.
- Implementing client-side order IDs to ensure that if the connection drops during execution, the system can definitively check if the order was filled upon restart, preventing duplicate market orders.
