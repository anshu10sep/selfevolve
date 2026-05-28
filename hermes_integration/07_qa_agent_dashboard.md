# QA Agent End-to-End Testing

## Target Component
`src/agents/qa_agent.py` and Dashboard UI

## Architecture Context
Our system includes a front-end dashboard (`dashboard/`) for visualization. Ensuring this dashboard reflects accurate, real-time data after every code evolution is difficult. Traditional unit tests don't verify visual regressions, and maintaining Selenium/Cypress suites is extremely brittle as the UI evolves.

## Approaches

### Approach 1: Generated Selenium Scripts
The QA agent writes and maintains traditional Python/Selenium test scripts that run in CI/CD.
- **Pros**: Deterministic, integrates well with traditional CI/CD pipelines.
- **Cons**: Highly brittle. As the dashboard evolves, the selectors break constantly, requiring constant test rewrites.

### Approach 2: Hermes Vision + Browser Automation
Utilize Hermes' browser control combined with its multimodal vision capabilities. The QA agent instructs Hermes to navigate to the dashboard, "look" at the rendered page via screenshots, and semantically verify if the data aligns with the expected database state (e.g., "Does the portfolio chart show a positive slope?").
- **Pros**: Impervious to DOM changes. It tests the dashboard exactly how a human portfolio manager would evaluate it.
- **Cons**: Vision API calls are more expensive and time-consuming than headless DOM checks.

## Recommendation: Approach 2 (Hermes Vision E2E)
Given that the codebase self-evolves, rigid DOM-based testing is a massive bottleneck. Semantic visual testing via Hermes guarantees that the dashboard remains usable for the human operator regardless of underlying HTML/CSS changes.
