# PR Generation and Review Flow

The ultimate output of the Jarvis system is usually a Pull Request (PR) containing code changes. The architecture handles this via a multi-agent workflow.

## The Flow

1. **Code Generation**: A Coder Agent finishes its task in its sandbox and generates a git patch.
2. **Commit & Push**: The agent uses the Integration Service to create a new branch and push the commit.
3. **Draft PR Creation**: The agent opens a PR marked as "Draft".
4. **Handoff**: A message is placed on the messaging bus: `pr_ready_for_review`.
5. **Review Phase**: A Reviewer Agent picks up the message, analyzes the PR diff, and leaves inline comments via the GitHub API.
6. **Iterate**: If the Reviewer requests changes, the PR is routed back to the Coder Agent's queue.
7. **Finalization**: Once approved by the Reviewer Agent, the PR is marked "Ready for Review" for a human (the Owner) to perform the final merge.

## Dashboard Visualization
This flow is visualized as a Kanban board or Pipeline view on the Owner's Dashboard.
- Columns: `In Progress` -> `Draft PR` -> `Under Review` -> `Ready for Owner`.
- The owner can click on any card to instantly see the PR diff right inside the dashboard.
- **Action**: The owner can click `[Merge PR]` directly from the dashboard, completing the lifecycle.
