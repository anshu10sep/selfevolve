# Infrastructure Deployment Architecture

## Target Component
Overall System Deployment and Topology

## Architecture Context
The defining feature of the Self-Evolving trading architecture is its Deterministic Python DAG, which bypasses LLM latency for trade execution. Integrating Hermes—a heavily LLM-orchestrated framework—poses a fundamental architectural question: How do we combine them without compromising execution speed?

## Approaches

### Approach 1: Full Hermes Framework Orchestration (Replace DAG)
Convert the entire system to run inside Hermes. Hermes becomes the central orchestrator, managing the market schedules, executing the trades, and spinning up subagents.
- **Pros**: Unified codebase, native multi-platform support across the entire app.
- **Cons**: FATAL. Placing an LLM orchestrator in the critical path for live trade execution introduces unpredictable latency and single points of failure. It violates the core tenets of our architecture.

### Approach 2: Hybrid Edge Architecture (DAG Core + Hermes Peripheral Workers)
Maintain the `main.py` Python DAG as the immutable core. The core manages the schedule, executes trades, and aggregates signals deterministically. Hermes is deployed as a suite of "Peripheral Workers". The DAG communicates with Hermes via API/RPC for specific, asynchronous tasks (e.g., "Run this backtest in a sandbox", "Scrape this SEC filing", "Send this alert to Discord").
- **Pros**: Best of both worlds. Lightning-fast deterministic trade execution, combined with the extreme flexibility, safety, and multimodal capabilities of Hermes for research and evolution.
- **Cons**: Requires managing two distinct architectural paradigms simultaneously.

## Recommendation: Approach 2 (Hybrid Edge Architecture)
This is the only viable path for a quantitative trading system. The core execution engine must remain mathematically deterministic. Hermes will act as our highly advanced R&D department, SRE, and communications hub, entirely decoupled from the millisecond-sensitive execution path.
