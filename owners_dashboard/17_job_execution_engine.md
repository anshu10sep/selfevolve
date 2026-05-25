# Job Execution Engine

The Job Execution Engine is the secure, isolated environment where an agent actually performs its assigned task.

## Sandbox Environment

To prevent rogue agents from damaging the host system, every job is executed within an ephemeral sandbox.
- **Technology**: Docker containers or Firecracker microVMs.
- **Capabilities**:
  - Contains a snapshot of the code repository.
  - Has access to necessary language runtimes (Python, Node.js).
  - Can execute bash commands.
- **Restrictions**:
  - Network access is heavily filtered (can only reach approved domains like github.com or npmjs.com).
  - Memory and CPU limits are hard-capped.

## Execution Flow

1. Agent pulls a job from the queue.
2. The Agent Manager provisions a fresh sandbox.
3. The Agent executes its loop inside the sandbox (read file -> prompt LLM -> write file -> run tests).
4. Upon job completion, the agent extracts the `diff` (patch).
5. The sandbox is destroyed, ensuring no state leakage between jobs.

## Dashboard Controls
From the dashboard, the owner can:
- View the live standard output (stdout/stderr) of a specific executing sandbox.
- **Action**: `[Terminate Sandbox]` - Instantly kills the container if the agent goes rogue or loops infinitely.
