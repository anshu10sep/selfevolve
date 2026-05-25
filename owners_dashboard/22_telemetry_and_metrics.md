# Telemetry and Metrics

Telemetry is the lifeblood of the Watchdog service and the primary data source for the Owner's Dashboard.

## Core Metrics Tracked

1. **Infrastructure Level**: CPU, RAM, Network I/O of the host machines and individual agent sandboxes.
2. **Application Level**: API latency, Queue depth, Database query times.
3. **AI / Model Level**: 
   - Token usage (Prompt vs. Completion tokens).
   - Inference latency (Time to First Token).
   - Model error rates (e.g., JSON parsing failures).

## The Telemetry Pipeline
1. Agents and services emit OpenTelemetry spans.
2. An OTel Collector aggregates the spans.
3. Metrics are stored in a Time-Series Database (e.g., Prometheus).
4. The Watchdog queries the TSDB to update its live state.

## Dashboard Visualization
The dashboard translates raw telemetry into understandable business metrics.
- Instead of showing "Tokens/sec", it might show "Estimated Cost per Job".
- Provides historical graphs (e.g., "Agent Success Rate over the last 7 days") to help the owner identify trends.
