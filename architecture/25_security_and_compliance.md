# Security, Compliance, and Auditability

## Secret Management
- **API Keys**: Alpaca API keys, LLM provider tokens (OpenAI, Anthropic), and data feed credentials must never be hardcoded.
- **Vault Integration**: Utilizing secure secret managers (e.g., HashiCorp Vault, AWS Secrets Manager, or local `.env` strategies in MVP) to inject credentials dynamically at runtime.

## Regulatory Compliance
- While the $100 capital base operates in a cash account exempt from PDT, the system strictly logs all transactions to prove compliance with T+1 settlement and absence of Good Faith Violations.

## Immutable Audit Logging
- Every decision made by the AI—specifically the final Pydantic output from the Judge Agent and the Human-in-the-Loop approval/rejection signals—is logged into an immutable database.
- This creates a comprehensive paper trail detailing the exact dialectical reasoning, market context, and explicit authorization behind every executed trade, satisfying internal governance and external regulatory inquiries.
