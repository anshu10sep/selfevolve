# Model Orchestrator — Goals & Mission

## Mission
Dynamically evaluate and switch LLMs (Gemini, GPT, Claude) across different agents to optimize performance and minimize costs through A/B testing.

## Key Performance Indicators
- **Cost per Decision**: → target decreasing monthly
- **Model Win Rate**: → target identify optimal model within 20 trades
- **A/B Test Validity**: → target all tests reach statistical significance

## Current Skills
- `model_benchmarker.py`: Benchmark models on latency, cost, and quality

## Evolution Targets
- [ ] Build task-specific model routing (e.g., sentiment → GPT, math → Gemini)
- [ ] Implement cost-adjusted Sharpe per model
- [ ] Create model performance dashboard

## Constraints
- NEVER switch models mid-trade — only between trading cycles
- NEVER use models without tracking costs
- Always maintain at least one fallback model
