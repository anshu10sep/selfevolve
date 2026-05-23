# Orchestration Framework: LangGraph

## The Necessity of Deterministic Orchestration
Constructing an infrastructure where disparate AI agents converse, deliberate on risk, and generate revenue requires an orchestration framework that transcends simple linear prompting. In live trading environments, deterministic execution, absolute traceability, and reliable state recovery are non-negotiable mandates.

## Evaluating Alternatives: CrewAI vs AutoGen
- **CrewAI**: Emphasizes a role-centric architecture. While effective for content generation, its simplicity abstracts away the granular orchestration details required for high-stakes financial execution.
- **AutoGen**: Champions a conversation-centric model. Flexible, but structurally less formal and susceptible to unpredictable conversation loops and sudden token cost spikes, rendering it suboptimal for strict algorithmic trading.

## Selection: LangGraph
LangGraph is selected as the primary architectural spine because it treats agents and workflows as nodes within a mathematically rigid graph.
- **Persistent State Management**: Natively provides state-based memory with explicit checkpointing. If a server process crashes during order execution, LangGraph ensures recovery without duplicate transactions.
- **Cyclical Workflows**: Enables cyclical workflows, allowing agents to continuously critique, verify, and improve their outputs over time—a fundamental prerequisite for the system's self-evolving requirement.
