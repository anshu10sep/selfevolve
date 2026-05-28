# Performance Analyst Reporting

## Target Component
`src/agents/performance_analyst_agent.py`

## Architecture Context
At market close, the system generates performance reports detailing PnL, strategy efficacy, and risk metrics. Currently, this relies heavily on text generation and markdown files pushed to the repository or sent via Telegram. 

## Approaches

### Approach 1: Markdown-only Summarization
Continue generating extensive text-based markdown reports and pushing them to the git repository.
- **Pros**: Clean, parsable, git-versioned.
- **Cons**: Difficult to digest quickly. Institutional portfolio managers rely on tearsheets and graphs, not walls of markdown text.

### Approach 2: Hermes Image Generation & PDF Rendering
Leverage Hermes to dynamically generate rich visual tearsheets. The Performance Analyst outputs quantitative metrics; Hermes uses its image generation and document rendering capabilities to compile a professional, graphical PDF report (including dynamically generated equity curves and drawdown heatmaps) and delivers it seamlessly via the preferred messaging channel.
- **Pros**: Delivers a highly professional, institutional-grade product to the user.
- **Cons**: Adds complexity to the reporting pipeline.

## Recommendation: Approach 2 (Hermes Visual Reporting)
A trading system is only as good as its observability. Delivering rich, graphical daily tearsheets drastically improves user trust and aligns with the system's "institutional hedge fund" aesthetic and functionality.
