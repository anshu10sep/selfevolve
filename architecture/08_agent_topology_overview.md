# Agent Topology and Analytical Ecosystem

## Hierarchical Multi-Agent Pattern
To mirror the rigorous operational structure of an institutional quantitative hedge fund, the system utilizes a hierarchical multi-agent pattern. The flow of data is strictly managed, ensuring raw market data is comprehensively synthesized before reaching the execution layer.

## Core Topology
1. **Primary Autonomous Orchestrator (Main Agent)**: The gateway. Monitors system state, holds user constraints, and invokes sub-workflows based on market conditions.
2. **Deep Research Sub-Agents**: Parallel agents executing specific analytical domains (Fundamental, Technical, Sentiment, Macro).
3. **The Debate Nodes (Bull & Bear)**: Enforces dialectical reasoning. Processes aggregated research from opposing perspectives to eliminate confirmation bias.
4. **The Judge (Risk Manager)**: Synthesizes the debate against $100 portfolio constraints to output strict Pydantic execution schemas.
5. **Human-in-the-Loop (HITL) Checkpoint**: Acts as a regulatory safeguard for anomalous events before bridging to the execution API.

This topology guarantees that no single LLM prompt is responsible for both analysis and execution, segregating responsibilities to minimize hallucinations and enforce strict risk governance.
