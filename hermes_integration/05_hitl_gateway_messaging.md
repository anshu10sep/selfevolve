# Human-In-The-Loop (HITL) Omnichannel Messaging

## Target Component
`src/core/hitl_gateway.py` and `integrations/telegram_bot.py`

## Architecture Context
Currently, the system relies exclusively on a Telegram bot for alerts and Human-In-The-Loop approvals (e.g., approving a large trade or a newly evolved strategy). While effective, restricting the system to a single platform limits the availability of the portfolio manager.

## Approaches

### Approach 1: Custom Multi-API Integration
Write manual integrations for Discord, Slack, Signal, and WhatsApp directly into the `hitl_gateway.py`.
- **Pros**: Full control over the integration code and API formatting.
- **Cons**: High maintenance overhead; APIs change frequently, and managing state across 5 messaging platforms is complex.

### Approach 2: Hermes Multi-Platform Hub
Hermes natively supports "Living Where You Do," with out-of-the-box integrations for Telegram, Discord, Slack, WhatsApp, Signal, and Email. By routing our HITL gateway through Hermes, we get omnichannel presence instantly. 
- **Pros**: Immediate access to all platforms. A conversation started on Slack can seamlessly transition to WhatsApp if the user leaves their desk.
- **Cons**: Adds Hermes as a dependency in the critical path for manual trade approvals.

## Recommendation: Approach 2 (Hermes Multi-Platform Hub)
The ability to transition context across platforms natively solves the "always-on" requirement for the portfolio manager. By utilizing Hermes as the messaging layer, the system can reach the user anywhere without writing boilerplate API integration code.
