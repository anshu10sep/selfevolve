# Strategy Researcher Delegation

## Target Component
`src/agents/strategy_researcher.py`

## Architecture Context
The Strategy Researcher is responsible for backtesting new hypotheses and generating novel trading strategies. This is a highly token-intensive, long-running process that involves reading historical data, writing backtest scripts, and analyzing results. Running this synchronously risks blocking the main event loop or consuming excessive resources on the primary node.

## Approaches

### Approach 1: Synchronous RPC Calls
The orchestrator calls the strategy researcher, which blocks and runs the backtesting script locally, returning the results once finished.
- **Pros**: Architecturally simple; state is easy to manage.
- **Cons**: Blocks system resources; risks timeouts if the backtest takes hours to complete.

### Approach 2: Asynchronous Hermes Sub-agent Swarm
Utilize Hermes' capability to delegate and parallelize. The main system dispatches a high-level goal to Hermes. Hermes then spins up an isolated sub-agent (or a swarm of them) with their own dedicated conversations and terminals. These sub-agents run the backtests in the background and only message the primary event bus upon completion.
- **Pros**: Zero-context-cost pipelines. The main trading DAG remains ultra-lean and fast while heavy research happens in an isolated background thread.
- **Cons**: Requires robust asynchronous messaging to stitch the results back into the main pipeline.

## Recommendation: Approach 2 (Asynchronous Swarm)
This perfectly aligns with our goal of maintaining a low-latency execution DAG. Delegating heavy, multi-step backtesting logic to Hermes sub-agents ensures the primary trading system is never blocked.
