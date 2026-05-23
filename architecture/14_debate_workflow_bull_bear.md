# The Debate Workflow (Bull & Bear)

## Countering Confirmation Bias
A significant vulnerability in LLMs deployed for financial forecasting is confirmation bias—generating justifications for a preconceived conclusion. The Debate Workflow is a highly deterministic LangGraph state machine designed specifically to counter this by enforcing dialectical reasoning.

## The Bull Persona
1. **Objective**: Actively searches the aggregated research for growth catalysts, competitive advantages, and bullish technical signals.
2. **Output**: Generates a quantified optimism score (0-10), backed entirely by empirical evidence gathered by the Deep Research sub-agents.

## The Bear Persona
1. **Objective**: Hard-coded to process the identical underlying research from a deeply pessimistic perspective. Acts as an internal auditor.
2. **Output**: Dismantles the Bull's thesis by highlighting structural debt risks, bearish technical divergences, poor macro conditions, and downside potential, culminating in a pessimism score (0-10).

## Workflow Execution
These opposing arguments are not executed independently; they are aggregated into a single dialectical state and passed simultaneously to the Judge Agent, ensuring every trade has been aggressively stress-tested before capital is risked.
