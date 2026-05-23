# Alpaca API Integration for Fractional Trading

## Enabling Micro-Capital Execution
Executing a fractional tranching strategy requires a brokerage API that natively supports granular algorithmic execution. The **Alpaca Trading API** is selected as it is engineered specifically for sophisticated algorithmic trading and supports the required fractional infrastructure.

## Fractional Share Trading Mechanics
Through the Alpaca Broker API, developers can execute algorithmic fractional trading with minimum order sizes as low as $1 across more than 2,000 U.S. equities.

- **Notional Order Routing**: The integration is achieved by overriding traditional quantity inputs (number of shares) and utilizing the `notional` parameter within the POST order submission endpoint.
- **Precision Allocation**: By submitting a notional order, the system instructs the broker to purchase a specific dollar amount (e.g., $10) of an asset, resulting in the precise allocation of a fractional share quantity (e.g., 0.078 shares).

## Key Implementation Details
- Ensure API calls to Alpaca accurately track fractional quantities for stop-loss and take-profit orders.
- Handle partial fills and bid-ask slippage correctly within the state management module to ensure the internal portfolio ledger exactly matches the broker's clearing records.
