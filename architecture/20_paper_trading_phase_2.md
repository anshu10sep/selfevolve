# Deployment Phase 2: Paper Trading

## Forward-Testing in Sandbox Environments
Phase 2 transitions the architecture into a live, simulated environment using the Alpaca Broker API's native paper trading functionality (`paper=True`). This provides real-time market data and order execution simulation with zero financial risk.

## Core Objectives
- **Mechanical Execution**: Observe the exact mechanical execution of fractional notional order routing using a synthetic $100 balance.
- **T+1 Settlement Stress Test**: Exhaustively validate the Portfolio Management Agent's ability to compartmentalize the synthetic $100 capital into rolling tranches. It must perfectly track settled vs. unsettled funds to definitively prevent simulated Good Faith Violations over a multi-week sprint.

## Observability and Cost
Concurrently, node-level tracing and observability metrics are established during this phase to:
- Rigorously monitor LLM token costs.
- Identify silent degradation in output quality over extended operational periods.
- Ensure the system remains economically viable before committing real capital.
