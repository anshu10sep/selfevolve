# SelfEvolve — Evolution System Design Documents

> **Purpose**: These documents define the production-ready evolution system for SelfEvolve.
> They cover the complete feedback loop from trade execution → prediction → resolution → Brier scoring → trust updates → prompt evolution.

## Document Index

| # | Document | Purpose |
|---|----------|---------|
| 01 | [Architecture Overview](01_architecture_overview.md) | End-to-end evolution architecture and data flow |
| 02 | [Prediction Lifecycle](02_prediction_lifecycle.md) | Trade → Prediction → Resolution pipeline |
| 03 | [Brier Scoring & Calibration](03_brier_scoring.md) | Proper scoring rules, calibration, cold-start |
| 04 | [Trust Weight System](04_trust_weight_system.md) | Agent trust decay, boost, and ensemble weighting |
| 05 | [Prompt Evolution](05_prompt_evolution.md) | Shadow testing, A/B testing, prompt promotion |
| 06 | [Strategy Backtesting](06_strategy_backtesting.md) | Walk-forward optimization, regime-aware testing |
| 07 | [Market Regime Detection](07_regime_detection.md) | Regime classification, adaptive behavior |
| 08 | [Concept Drift Detection](08_drift_detection.md) | ADWIN, DDM, automated retraining triggers |
| 09 | [Position Sizing](09_position_sizing.md) | Kelly criterion, Brier-calibrated sizing |
| 10 | [Operational Scoring](10_operational_scoring.md) | Non-prediction agent trust metrics |
| 11 | [Current Bugs & Gaps](11_current_bugs.md) | Diagnosed issues blocking the evolution loop |
| 12 | [Implementation Roadmap](12_implementation_roadmap.md) | Phased plan to make evolution production-ready |

## Current State (May 2026)

The evolution system has **excellent architecture** but is currently **inert**:
- 0 predictions resolved across 21 agents
- Brier scores never computed
- Trust weights never updated
- Prompt evolution never triggered
- The entire reflexion loop runs on zero signal

These documents define the fixes and improvements needed to make it work.
