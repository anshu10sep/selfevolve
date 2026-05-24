# Alpaca API Integration Implementation Plan

## 1. Webhook-Driven Reconciliation
Polling the broker API for order status creates hanging state vulnerabilities, race conditions, and consumes valuable rate-limit tokens. Order reconciliation must be purely event-driven.

### Implementation Details:
*   **FastAPI Webhook Listener**: A lightweight, independent FastAPI service dedicated solely to listening for Alpaca push notifications (`fill`, `canceled`, `rejected`).
*   **Atomic Ledger Updates**: The webhook listener is the **exclusive** component authorized to write updates to the SQLite/Postgres ledger. The CrewAI flow submits the order, records the `client_order_id`, and immediately terminates. State synchronization occurs deterministically via database transactions upon webhook receipt.

## 2. Immutable Infrastructure Logic
Allowing an LLM (the Meta-Review Crew) to autonomously rewrite complex asynchronous Python infrastructure (like WebSockets or database connections) risks introducing fatal deadlocks and connection storms.

### Implementation Details:
*   **Strict Evolutionary Boundaries**: System evolution is strictly confined to **Prompts, Agent Roles, and Strategy Parameters**.
*   **Code Immutability**: All core infrastructure code (`asyncio` daemons, execution wrappers, FastAPI listeners) is rendered immutable to the AI and can only be updated via human-reviewed PRs.

## 3. Decoupled Microservices Architecture
The market data feed and the orchestration logic must be isolated so that a failure in the LLM reasoning chain does not blind the system to live market events.

### Implementation Details:
*   **Market Data Service (Docker)**: A dedicated container running the Python `asyncio` WebSocket daemon. It maintains a persistent connection to Alpaca's `sip` stream.
*   **Redis Pub/Sub**: The Market Data Service broadcasts significant volume/price events to a Redis Pub/Sub channel.
*   **CrewAI Orchestration Service**: Subscribes to the Redis channel. It consumes events and spawns targeted agent tasks. If the CrewAI service crashes, the data stream remains uninterrupted.

## 4. API Rate Limit and Tool Handling
Transient Alpaca API failures (HTTP 429, 503) must be handled gracefully without crashing the active Crew execution.

### Implementation Details:
*   **RateLimitManager**: A custom wrapper sits between CrewAI tools and the API, implementing exponential backoff.
*   **Sub-Crew Pausing**: If a rate limit is hit, the `Manager Agent` pauses the active thread and redirects compute resources to offline tasks (e.g., historical analysis) until the window clears.
*   **Notional Forced Routing**: To maximize the $100 base, the `AlpacaOrderSubmissionTool` intercepts standard quantity inputs and forces them into `notional` (dollar value) parameters, ensuring fractional execution.

## 5. Mermaid Diagram: Decoupled API Architecture

```mermaid
graph TD
    subgraph Market Data Service (Docker)
        A[Alpaca WebSocket] -->|asyncio| B[Daemon]
        B -->|Broadcast| C((Redis Pub/Sub))
    end

    subgraph CrewAI Orchestrator
        C -->|Subscribe| D[Event Consumer]
        D --> E[CrewAI Strategy Flow]
        E --> F[AlpacaOrderSubmissionTool]
    end

    subgraph Execution & Reconciliation
        F -->|POST Order| G[Alpaca API]
        G -->|Push Webhook| H[FastAPI Listener]
        H -->|Atomic Write| I[(PostgreSQL Ledger)]
    end
```
