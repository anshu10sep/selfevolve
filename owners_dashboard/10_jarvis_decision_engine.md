# Jarvis Decision Engine

The Decision Engine is the internal logic layer of the Jarvis Core that evaluates states and chooses the next best action.

## The Decision Loop

The engine operates on a continuous Observe-Orient-Decide-Act (OODA) loop:

1. **Observe**: Ingests state data from the Watchdog and State Storage. (e.g., "Agent-12 finished coding feature X, but the tests failed").
2. **Orient**: Contextualizes the observation against the global goal. (e.g., "Feature X is a blocker for Feature Y").
3. **Decide**: Formulates a plan to resolve the situation. (e.g., "Spawn a debugging agent to analyze the failed tests").
4. **Act**: Dispatches the required API calls to the Agent Manager.

## Heuristics and Policies
The Decision Engine is governed by owner-defined policies:
- **Cost Policy**: Prefer smaller, cheaper agents for simple tasks.
- **Speed Policy**: Parallelize tasks aggressively if the goal is time-sensitive.
- **Quality Policy**: Always enforce a peer-review step by a separate agent before pushing a PR.

## Dashboard Controls
From the Owner's Dashboard, the owner can interact with the Decision Engine by:
- Adjusting the active policies (sliding a scale between "Cost" and "Speed").
- Manually overriding a decision (e.g., aborting a plan Jarvis just formulated).
- Viewing the decision tree (a visual flowchart of *why* Jarvis made a specific choice).
