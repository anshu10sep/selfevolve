# 05 — Prompt Evolution

## How Prompts Evolve

Each agent has two prompt sections:
1. **Identity Core** — IMMUTABLE. Defines the agent's role, expertise, output format.
2. **Strategic Nuance** — MUTABLE. Contains learned behavioral rules from the evolution loop.

Evolution only modifies Strategic Nuance. Identity Core is protected by Pydantic domain isolation validators.

## Current Pipeline

```
Underperformer Detected (Brier > 0.35 or trust < 0.5)
    → MetaReviewAgent generates post-mortem
    → MetaReviewAgent proposes new Strategic Nuance
    → Domain Isolation Validator checks safety
    → Create candidate prompt_version (is_active=False)
    → Shadow Crew runs candidate in parallel with production
    → After SHADOW_MIN_TRADES (20), run Welch's t-test
    → If p < 0.05 and shadow is better → PROMOTE
    → If p < 0.05 and shadow is worse → DISCARD
    → Otherwise → CONTINUE_TESTING
```

## Current Problems

### 1. Shadow Testing Never Gets Data
Since predictions are never resolved (Bug 5 from earlier), shadow predictions also have no outcomes. Welch's t-test never runs because both `shadow_errors` and `prod_errors` have < 5 entries.

### 2. No Diversity in Prompt Mutations
The MetaReviewAgent generates exactly ONE candidate per underperformer per cycle. If that candidate is rejected, we wait until the next cycle to try again. Professional prompt evolution (DSPy, PromptBreeder) generates multiple candidates in parallel.

### 3. No Gradient Signal
The post-mortem text is free-form LLM output. There's no structured signal telling the mutator *which specific rule* underperformed. DSPy-style optimization uses the metric gradient to guide prompt changes.

### 4. Rules Accumulate Without Pruning
`MAX_RULES_PER_AGENT = 3`, but there's no mechanism to remove stale rules. A rule that was useful in a bull market may hurt in a bear market.

## Best Practices from Research

### DSPy-Inspired Optimization

```python
# Declarative approach: define what "good" looks like
class TradingAnalysis(dspy.Signature):
    """Given market data, produce a calibrated prediction."""
    market_data = dspy.InputField()
    prediction = dspy.OutputField(desc="Probability 0.0-1.0 of profitable trade")

# Optimize with a metric
optimizer = dspy.BootstrapFewShot(
    metric=lambda pred, gold: brier_score(pred.prediction, gold.outcome),
    max_bootstrapped_demos=4,
)
compiled = optimizer.compile(TradingAnalysis, trainset=historical_trades)
```

### TextGrad-Inspired Refinement

```python
# Use LLM as a "gradient oracle"
feedback = llm.invoke(
    f"Agent {role} predicted {pred:.2f} for {ticker}, outcome was {outcome}.\n"
    f"Current rules:\n{current_nuance}\n\n"
    f"Which specific rule led to this error? "
    f"How should it be modified? Be precise."
)
# Apply the "gradient" as a targeted rule edit
```

### PromptBreeder-Inspired Diversity

```python
# Generate N candidates, not just 1
MUTATION_STRATEGIES = [
    "add_new_rule",           # Generate a new rule based on post-mortem
    "modify_worst_rule",      # Edit the rule most correlated with errors
    "remove_stale_rule",      # Remove rules inactive for 2+ weeks
    "crossover_from_top",     # Copy successful rule from a top-performing agent
    "hypermutation",          # Radical rewrite of all rules
]

candidates = []
for strategy in MUTATION_STRATEGIES:
    candidate = await generate_candidate(agent, strategy, post_mortem)
    candidates.append(candidate)

# Run all candidates in shadow simultaneously
```

## Proposed Design

### Phase 1: Fix Foundation
- Fix prediction resolution so shadow predictions get outcomes
- Ensure `is_shadow=True` predictions go through same resolution pipeline

### Phase 2: Multi-Candidate Evolution
```python
class PromptEvolutionEngine:
    async def evolve_agent(self, role, brier, post_mortem):
        candidates = []

        # Strategy 1: Targeted rule edit
        candidates.append(await self.edit_worst_rule(role, post_mortem))

        # Strategy 2: New rule from post-mortem
        candidates.append(await self.add_rule(role, post_mortem))

        # Strategy 3: Cross-pollination from top performer
        top_agent = self.get_top_performer_in_domain(role)
        if top_agent:
            candidates.append(await self.crossover(role, top_agent))

        # All candidates enter shadow testing simultaneously
        for candidate in candidates:
            if self.validate_domain_isolation(candidate):
                self.create_shadow_version(role, candidate)
```

### Phase 3: Automatic Rule Lifecycle
```python
class RuleLifecycleManager:
    def prune_stale_rules(self, role):
        """Remove rules that haven't contributed to decisions in 2 weeks."""
        rules = get_current_rules(role)
        for rule in rules:
            if rule.last_triggered < now() - timedelta(days=14):
                archive_rule(rule)
                log_evolution_event("RULE_PRUNED", rule)

    def promote_proven_rules(self, role):
        """Share rules that work across multiple agents."""
        rules = get_rules_with_positive_impact(role)
        for rule in rules:
            if rule.impact_score > 0.1 and rule.confidence > 0.95:
                broadcast_rule_to_similar_agents(rule)
```

## Statistical Testing

### Current: Welch's t-test
Good for comparing means of two independent samples with unequal variance. Requires ≥20 trades per group (SHADOW_MIN_TRADES).

### Alternative: Sequential Testing (SPRT)
Doesn't require a fixed sample size. Can make promote/discard decisions earlier:

```python
# Sequential Probability Ratio Test
# H0: shadow is same as production
# H1: shadow is better by at least delta
likelihood_ratio = compute_likelihood_ratio(shadow_results, prod_results)
if likelihood_ratio > upper_threshold:
    return "PROMOTE"   # Strong evidence shadow is better
elif likelihood_ratio < lower_threshold:
    return "DISCARD"   # Strong evidence shadow is worse
else:
    return "CONTINUE"  # Need more data
```

**Advantage**: Can promote a clearly-better prompt after just 10 trades instead of waiting for 20.
