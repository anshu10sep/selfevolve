# SelfEvolve Agent Onboarding Documentation

Welcome to the SelfEvolve autonomous trading system! This document outlines the current agent structure, their roles, and their respective skills.

## Agent Roles and Skills

### Auditor
**Directory:** `agents/skills/auditor/`

#### Available Skills:
- `audit_logs.py`
- `compliance_check.py`
- `security_review.py`
- `skills.py`

### Bear
**Directory:** `agents/skills/bear/`

#### Available Skills:
- `identify_bearish_signals.py`
- `risk_assessment.py`
- `short_position_analysis.py`

### Bull
**Directory:** `agents/skills/bull/`

#### Available Skills:
- `growth_potential_assessment.py`
- `identify_bullish_signals.py`
- `long_position_analysis.py`

### Crypto Analyst
**Directory:** `agents/skills/crypto_analyst/`

#### Available Skills:
- `analyze_blockchain_data.py`
- `evaluate_crypto_projects.py`
- `predict_crypto_trends.py`

### Crypto Sentiment
**Directory:** `agents/skills/crypto_sentiment/`

#### Available Skills:
- `analyze_crypto_news.py`
- `gauge_market_sentiment.py`
- `monitor_crypto_social_media.py`

### Cso
**Directory:** `agents/skills/cso/`

#### Available Skills:
- `incident_response.py`
- `security_policy_enforcement.py`
- `threat_detection.py`

### Cto
**Directory:** `agents/skills/cto/`

#### Available Skills:
- `roadmap_planning.py`
- `system_architecture_review.py`
- `tech_stack_evaluation.py`

### Cto Crypto
**Directory:** `agents/skills/cto_crypto/`

#### Available Skills:
- `blockchain_integration.py`
- `defi_protocol_analysis.py`
- `smart_contract_audit.py`

### Developer
**Directory:** `agents/skills/developer/`

#### Available Skills:
- `debug_code.py`
- `refactor_code.py`
- `test_code.py`
- `write_code.py`

### Fundamental Analyst
**Directory:** `agents/skills/fundamental_analyst/`

#### Available Skills:
- `analyze_financial_statements.py`
- `assess_economic_indicators.py`
- `evaluate_company_news.py`
- `skills.py`

### Jarvis
**Directory:** `agents/skills/jarvis/`

#### Available Skills:
- `agent_planning.py`
- `code_generation.py`
- `github_ops.py`
- `system_audit.py`
- `update_onboarding_docs.py`

### Journaling
**Directory:** `agents/skills/journaling/`

#### Available Skills:
- `log_market_events.py`
- `record_decisions.py`
- `summarize_daily_activity.py`

### Judge
**Directory:** `agents/skills/judge/`

#### Available Skills:
- `evaluate_proposals.py`
- `make_final_decision.py`
- `resolve_conflicts.py`

### Macro Analyst
**Directory:** `agents/skills/macro_analyst/`

#### Available Skills:
- `analyze_global_economy.py`
- `assess_geopolitical_risks.py`
- `forecast_interest_rates.py`

### Meta Review
**Directory:** `agents/skills/meta_review/`

#### Available Skills:
- `evaluate_strategy_effectiveness.py`
- `propose_improvements.py`
- `review_agent_performance.py`

### Model Orchestrator
**Directory:** `agents/skills/model_orchestrator/`

#### Available Skills:
- `deploy_models.py`
- `monitor_model_performance.py`
- `retrain_models.py`

### Pr Reviewer
**Directory:** `agents/skills/pr_reviewer/`

#### Available Skills:
- `code_review.py`
- `pr_tools.py`
- `presubmit.py`
- `review_pipeline.py`

### Product
**Directory:** `agents/skills/product/`

#### Available Skills:
- `define_features.py`
- `gather_requirements.py`
- `roadmap_management.py`

### Qa
**Directory:** `agents/skills/qa/`

#### Available Skills:
- `execute_tests.py`
- `report_bugs.py`
- `write_test_cases.py`

### Sentiment Analyst
**Directory:** `agents/skills/sentiment_analyst/`

#### Available Skills:
- `analyze_news_articles.py`
- `gauge_market_mood.py`
- `monitor_social_media.py`

### Technical Analyst
**Directory:** `agents/skills/technical_analyst/`

#### Available Skills:
- `chart_pattern_recognition.py`
- `indicator_analysis.py`
- `predict_price_movements.py`

## How to Add a New Agent
1. Create a new directory under `agents/skills/` with the agent's name.
2. Add Python files (`.py`) for each skill the agent should possess.
3. Ensure each skill has proper docstrings and type hints.
4. Run the `update_onboarding_docs` skill to regenerate this documentation.

## How to Add a New Skill
1. Navigate to the specific agent's directory: `agents/skills/<agent_name>/`.
2. Create a new Python file for the skill (e.g., `new_skill.py`).
3. Implement the skill logic with clear docstrings.
4. Run the `update_onboarding_docs` skill to update the documentation.
===