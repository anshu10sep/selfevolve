# State Management and Database

The Jarvis ecosystem requires highly reliable state management to ensure that if a node fails, the system can recover without losing work.

## Database Technologies

1. **Relational Database (PostgreSQL)**
   - Used for: Agent metadata, job definitions, historical audit logs, owner user accounts.
   - Why: Strong ACID compliance ensures that a job is not assigned to two agents simultaneously.

2. **In-Memory Store (Redis)**
   - Used for: Task Queues, Pub/Sub messaging, real-time Watchdog state.
   - Why: Extremely low latency required for inter-agent communication and live dashboard updates.

3. **Vector Database (Pinecone / Milvus)**
   - Used for: Codebase embeddings, semantic search.
   - Why: Allows agents to quickly query the repository ("Find where the JWT token is validated") without re-reading the entire source tree.

## Dashboard Visibility
The Dashboard contains a "Storage & State" panel.
- Displays database health, current connection counts, and query latency.
- Allows the owner to trigger manual backups or view the schema migrations.
