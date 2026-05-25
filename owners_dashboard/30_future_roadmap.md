# Future Roadmap

The architecture is designed to be extensible. This document outlines the planned future capabilities of the Jarvis ecosystem.

## Phase 2: Multi-Project Orchestration
Currently, Jarvis focuses on a single repository. Future versions will allow the Owner's Dashboard to switch contexts between multiple discrete software projects, sharing learned heuristics across them.

## Phase 3: Proactive Threat Hunting
Integrating specialized "Security Agents" that autonomously penetration-test the codebase and infrastructure during idle periods, automatically generating PRs to patch vulnerabilities before they are exploited.

## Phase 4: Full Infrastructure Management
Allowing Jarvis to not only write code but to directly alter the Terraform/AWS configurations to deploy the new code to production without human intervention.

## Dashboard Implications
As new features are added, the Dashboard will evolve to include new node types (e.g., Security Scanners) and new visualization layers (e.g., a global portfolio view of multiple projects).
