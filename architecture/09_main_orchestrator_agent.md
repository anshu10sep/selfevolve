# The Autonomous Orchestrator (Main Agent)

## The Central Nervous System
The Main Agent acts as the central nervous system of the trading ecosystem. Constructed using advanced orchestration functions, it is designed for absolute autonomy. It views a vast array of proprietary tools, external API adapters, and custom sub-workflow wrappers.

## Core Responsibilities
- **Tool Composition**: Reasons about which tools to utilize, composes multiple tools in a single interactive turn, and synthesizes outputs. Does *not* execute trades directly.
- **Constraint Management (UserContext)**: Crucially, the Orchestrator holds the `UserContext` schema in its state. This includes:
  - Overall trading level constraints
  - Maximum position sizing limits
  - Risk tolerance profile (conservative, moderate, aggressive)
  - Real-time tracking of settled vs. unsettled funds (T+1 protocol)

## Workflow Triggering
When the Orchestrator detects a systemic catalyst or high-probability setup through continuous market feeds, it actively manages the delegation of tasks, automatically triggering the Deep Research Sub-Agents to conduct granular analysis before any financial decisions are considered.
