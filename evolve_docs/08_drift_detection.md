# 08 — Concept Drift Detection

## The Problem

A trading strategy that works today may stop working tomorrow because the market changed. **Concept drift** occurs when the statistical relationship between inputs (market data) and outputs (profitable trades) shifts over time.

Without drift detection, the system will:
1. Continue trading with a broken strategy
2. Accumulate losses before the next evolution cycle catches it
3. Waste evolution cycles trying to fix "bugs" that are actually regime shifts

## Types of Drift in Trading

| Type | Example | Speed |
|------|---------|-------|
| **Sudden** | Fed rate decision, earnings shock | Minutes |
| **Gradual** | Sector rotation, inflation trend | Weeks |
| **Recurring** | Seasonality, FOMC cycles | Periodic |
| **Incremental** | Strategy crowding, alpha decay | Months |

## Detection Methods

### 1. ADWIN (Adaptive Windowing)

Best for gradual drift. Maintains a variable-length window and shrinks it when a statistically significant change is detected.

```python
class ADWINDriftDetector:
    """Detect gradual performance drift using adaptive windowing."""

    def __init__(self, delta=0.002):
        self.delta = delta
        self.window = []
        self.total = 0.0
        self.variance = 0.0
        self.width = 0

    def add(self, value: float) -> bool:
        """Add a new observation. Returns True if drift detected."""
        self.window.append(value)
        self.width += 1
        self.total += value

        if self.width < 10:
            return False

        # Check for drift: compare two sub-windows
        for split in range(max(5, self.width // 4), self.width - 5):
            w0 = self.window[:split]
            w1 = self.window[split:]

            mu0 = sum(w0) / len(w0)
            mu1 = sum(w1) / len(w1)

            epsilon = self._hoeffding_bound(len(w0), len(w1))

            if abs(mu0 - mu1) >= epsilon:
                # Drift detected! Shrink window to recent data
                self.window = w1
                self.width = len(w1)
                self.total = sum(w1)
                return True

        return False

    def _hoeffding_bound(self, n0, n1):
        from math import log, sqrt
        m = 1.0 / (1.0/n0 + 1.0/n1)
        delta_prime = self.delta / log(self.width)
        return sqrt((1.0 / (2.0 * m)) * log(4.0 / delta_prime))
```

### 2. DDM (Drift Detection Method)

Best for sudden drift. Monitors error rate against a baseline.

```python
class DDMDriftDetector:
    """Detect sudden performance drift using DDM."""

    def __init__(self, warning_level=2.0, drift_level=3.0):
        self.warning_level = warning_level
        self.drift_level = drift_level
        self.n = 0
        self.p = 0.0  # Running error rate
        self.s = 0.0  # Running std dev
        self.p_min = float('inf')
        self.s_min = float('inf')
        self.in_warning = False

    def add(self, is_error: bool) -> str:
        """Add new prediction result. Returns 'OK', 'WARNING', or 'DRIFT'."""
        self.n += 1
        error = 1.0 if is_error else 0.0

        # Update running stats
        self.p += (error - self.p) / self.n
        self.s = (self.p * (1 - self.p) / self.n) ** 0.5

        # Update minimum
        if self.p + self.s < self.p_min + self.s_min:
            self.p_min = self.p
            self.s_min = self.s

        # Check thresholds
        if self.p + self.s > self.p_min + self.drift_level * self.s_min:
            self.reset()
            return "DRIFT"
        elif self.p + self.s > self.p_min + self.warning_level * self.s_min:
            self.in_warning = True
            return "WARNING"
        else:
            self.in_warning = False
            return "OK"

    def reset(self):
        self.n = 0
        self.p = 0.0
        self.s = 0.0
        self.p_min = float('inf')
        self.s_min = float('inf')
```

### 3. Page-Hinkley Test

Good for detecting mean shifts in streaming data:

```python
class PageHinkleyDetector:
    def __init__(self, threshold=50, min_instances=30, delta=0.005):
        self.threshold = threshold
        self.min_instances = min_instances
        self.delta = delta
        self.n = 0
        self.sum = 0.0
        self.x_mean = 0.0
        self.ph = 0.0
        self.ph_min = float('inf')

    def add(self, value: float) -> bool:
        self.n += 1
        self.x_mean += (value - self.x_mean) / self.n
        self.sum += value - self.x_mean - self.delta
        self.ph_min = min(self.ph_min, self.sum)

        if self.n < self.min_instances:
            return False

        return (self.sum - self.ph_min) > self.threshold
```

## Integration with SelfEvolve

### Per-Agent Drift Monitoring

```python
class AgentDriftMonitor:
    def __init__(self):
        self.detectors = {}  # {agent_role: ADWINDriftDetector}

    async def on_prediction_resolved(self, agent_role, predicted, actual):
        """Called every time a prediction is resolved."""
        if agent_role not in self.detectors:
            self.detectors[agent_role] = ADWINDriftDetector()

        error = (predicted - actual) ** 2  # Brier error for this prediction
        drift = self.detectors[agent_role].add(error)

        if drift:
            await self.handle_drift(agent_role)

    async def handle_drift(self, agent_role):
        """Respond to detected drift."""
        # 1. Alert
        await send_alert(f"⚠️ Performance drift detected for {agent_role}")

        # 2. Reduce trust immediately (don't wait for evolution cycle)
        from evolution.trust_updater import emergency_trust_reduction
        emergency_trust_reduction(agent_role, factor=0.8)

        # 3. Trigger immediate evolution cycle for this agent
        from evolution.evolution_runner import evolution_runner
        await evolution_runner._evolve_agent(agent_role, {
            "brier_score": 0.5,
            "trust_weight": 0.5,
            "name": agent_role,
            "reason": "drift_detected",
        })
```

### Strategy-Level Drift

```python
class StrategyDriftMonitor:
    """Monitor strategy performance for regime-induced drift."""

    def __init__(self):
        self.strategy_detectors = {}
        self.regime_detector = DDMDriftDetector()

    async def check_strategy_health(self):
        """Run every 30 minutes during market hours."""
        for strategy_name, detector in self.strategy_detectors.items():
            recent_trades = get_recent_strategy_trades(strategy_name, limit=20)

            for trade in recent_trades:
                is_error = trade["pnl"] < 0
                status = detector.add(is_error)

                if status == "DRIFT":
                    await self.deactivate_strategy(strategy_name)
                elif status == "WARNING":
                    await self.reduce_strategy_allocation(strategy_name)

    async def deactivate_strategy(self, name):
        """Temporarily remove strategy from active trading."""
        from agents.strategies.strategy_evolution import strategy_evolution_engine
        strategy_evolution_engine.deactivate(name)
        await send_alert(f"🛑 Strategy {name} deactivated — drift detected")
```

## Automated Responses to Drift

| Drift Level | Response | Timeline |
|-------------|----------|----------|
| **WARNING** | Reduce position sizes 50% | Immediate |
| **DRIFT** | Pause strategy, alert human | Immediate |
| **CONFIRMED** | Trigger evolution cycle | Within 5 min |
| **REGIME_CHANGE** | Rebalance all strategy weights | Within 15 min |
