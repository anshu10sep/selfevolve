# Evolution Engine Sandboxing

## Target Component
`src/evolution/bug_worker.py` and `src/agents/developer_agent.py`

## Architecture Context
The Self-Evolving trading architecture relies on an autonomous evolution engine where the `bug_worker` and `developer_agent` proactively identify issues, write Python code, and test fixes. Currently, executing LLM-generated code locally introduces severe security and stability risks. A rogue infinite loop or destructive file operation could crash the live trading daemon.

## Approaches

### Approach 1: Docker-in-Docker via Hermes
Utilize Hermes' built-in Docker sandbox backend. The `developer_agent` passes the proposed code to a local Hermes Docker container. Hermes executes the code, runs the test suite, and returns the stdout/stderr.
- **Pros**: Local execution, low latency, no external dependencies.
- **Cons**: Managing Docker-in-Docker state and networking can be complex and resource-intensive on the host machine.

### Approach 2: Modal Serverless Sandboxes via Hermes
Utilize Hermes' Modal backend integration. When code is generated, Hermes spins up an isolated serverless Modal environment in the cloud, executes the code, and streams the results back via RPC.
- **Pros**: True isolation (code runs off-server), infinitely scalable for parallel tests, zero local resource drain.
- **Cons**: Adds minimal network latency and relies on a third-party cloud provider (Modal).

## Recommendation: Approach 2 (Modal Serverless Sandboxes)
For an institutional-grade trading system, the core machine should only handle deterministic market execution. Offloading untrusted, LLM-generated code execution to Modal guarantees that the primary trading node remains 100% secure and uncompromised.
