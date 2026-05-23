# Settlement Mechanics and Violations

## Operating in a Cash Account Environment
Because the system starts with $100, it cannot use margin and must operate in a cash account. Cash accounts are exempt from intraday margin frameworks and the PDT rule, but introduce severe constraints governed by standard settlement cycles.

## T+1 Settlement Cycle
In a cash account, all securities purchased must be paid for in full prior to being sold, and capital is bound by the T+1 (Trade Date plus one business day) settlement cycle. 
- If a position is liquidated on Monday morning, the cash proceeds do not settle until Tuesday morning.
- Unsettled funds cannot be recklessly reinvested without triggering severe regulatory infractions.

## Regulatory Infractions to Avoid
### Good Faith Violation (GFV)
Triggered if the AI agent liquidates a profitable position, aggressively uses the unsettled funds to execute a secondary purchase, and subsequently liquidates that second position before the initial funds clear. Accumulating three GFVs within a rolling 12-month period results in an automatic 90-day account restriction.

### Freeriding Violation
Selling a security before sufficient funds have settled to cover the initial purchase constitutes a Freeriding violation.

## System Requirement
The AI architecture must internalize a flawless capital tracking module to monitor settled vs. unsettled cash precisely, ensuring complete compliance and uninterrupted operational velocity.
