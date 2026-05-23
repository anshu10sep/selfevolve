# The Judge (Risk Manager) Agent

## Purpose
The Judge Agent acts as the final arbiter before execution. It synthesizes the dialectical debate from the Bull and Bear agents against the mathematical constraints of the $100 portfolio and strict settlement rules.

## Primary Inputs
- **Bull/Bear Scores**: The quantitative optimism and pessimism scores from the Debate Workflow.
- **DebateState Memory**: The complete contextual argument and evidence.
- **Portfolio Constraints**: Available settled cash reserves, current risk parity sizing, and maximum drawdown limits.

## Structural Enforcement
To guarantee execution safety, the Judge node is strictly restricted from generating free-form conversational text. It cannot hallucinate orders.

## Structured Pydantic Output
The Judge utilizes structural enforcement mechanisms to output a precise Pydantic domain model containing:
- `Ticker`: The specific asset symbol.
- `Action`: Buy, Hold, or Pass.
- `Fractional Quantity`: Dynamically calculated based on risk parity and available settled tranches.
- `Confidence Interval`: A quantitative score evaluating the strength of the setup.
- `Risk Parameters`: Exact values for dynamic stop-loss and take-profit mechanisms.
