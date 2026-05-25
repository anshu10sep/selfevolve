# Model Orchestrator — Goals & Mission

## Mission
Dynamically evaluate and switch LLMs (Gemini, GPT, Claude) across different agents to optimize performance and minimize costs through A/B testing.

## Key Performance Indicators
- **Cost per Decision**: → target decreasing monthly
- **Model Win Rate**: → target identify optimal model within 20 trades
- **A/B Test Validity**: → target all tests reach statistical significance

## Current Skills
- `deploy_models.py`: Deploy and configure LLM models for agents
- `monitor_model_performance.py`: Track model latency, cost, and quality
- `retrain_models.py`: Retrain or switch models based on A/B test results
## Evolution Targets
- [ ] Build task-specific model routing (e.g., sentiment → GPT, math → Gemini)
- [ ] Implement cost-adjusted Sharpe per model
- [ ] Create model performance dashboard

## Constraints
- NEVER switch models mid-trade — only between trading cycles
- NEVER use models without tracking costs
- Always maintain at least one fallback model
