# Database Skills — Goals & Mission

## Mission
Manage Redis and PostgreSQL connections, execute queries, and handle database errors gracefully with retry logic and connection pooling.

## Key Performance Indicators
- **Connection Reliability**: → target 99.9% successful connections
- **Query Latency**: → target < 50ms for Redis operations
- **Error Recovery**: → target auto-recover from transient failures

## Current Skills
- `query_database.py`: Redis query operations with JSON serialization
- `manage_connections.py`: Connection management with retry logic and pooling
- `handle_errors.py`: Error handling, categorization, and diagnosis

## Evolution Targets
- [ ] Add PostgreSQL connection management
- [ ] Implement connection pool auto-scaling
- [ ] Build query performance monitoring

## Constraints
- NEVER expose connection credentials in logs
- NEVER leave connections open without timeout
- Always use exponential backoff for retries
