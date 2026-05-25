# System Overview

The **Jarvis Self-Evolving Agent System** is a complex, distributed AI architecture designed to autonomously manage, evolve, and orchestrate various agentic tasks. 

## Purpose
The primary purpose of the system is to provide a central intelligence (Jarvis) that monitors itself and its environment (via the Watchdog service), and spawns specialized agents to handle specific workflows, such as code generation, repository management, and PR reviews.

## Key Components
1. **Owner's Dashboard**: The single pane of glass for the system owner to visualize and control the entire architecture.
2. **Watchdog Service**: Monitors health, events, and metrics across the system.
3. **Jarvis Core Model**: The brain of the operation, capable of self-evolution and strategic decision-making.
4. **Agent Manager**: Responsible for spinning up, monitoring, and shutting down specialized agents.
5. **Job Execution Engine**: The underlying infrastructure that processes tasks queued by the agents.

## Core Philosophy
The architecture follows an **Event-Driven** and **Microservices-oriented** approach. The system is designed to be fully observable from a 10,000-foot view, with drill-down capabilities into every atomic component, all controllable via the Owner's Dashboard.
