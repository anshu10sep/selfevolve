# Human-in-the-Loop (HITL) Integration

## Risk Governance and Oversight
Deploying AI in financial markets requires stringent risk governance. While autonomous operation is the baseline, the system incorporates a Human-in-the-Loop (HITL) control flow for anomalous, high-impact events, treating HITL as a first-class citizen within the LangGraph architecture.

## The Approval Node
Situated directly between the Judge Agent's synthesis and the Alpaca API execution. Under normal parameters, it is an automated passthrough.

## Automatic Interrupt Triggers
The state graph immediately pauses and pings the user under these conditions:
- **Confidence Divergence**: If Bull and Bear scores are highly polarized and the Judge outputs a confidence score < 0.60.
- **Drawdown Limits**: If account equity falls by a specified percentage from its high-water mark, freezing capital deployment.
- **Anomalous Volatility Signatures**: Extreme intraday volatility, flash crashes, or macro shocks exceeding historical norms.

## User Interface and Resumption
When triggered, the system presents the user with a structured interface displaying the target asset, fractional sizing, stop-loss metrics, and a summarized risk assessment. The user can approve, reject, or modify. Following input, the LangGraph state machine resumes exactly where paused.
