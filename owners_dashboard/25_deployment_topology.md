# Deployment Topology

The Jarvis system is designed to be deployed on modern cloud-native infrastructure.

## Kubernetes Architecture

The entire ecosystem runs on a Kubernetes (K8s) cluster.

1. **Control Plane Namespace**: Contains the Jarvis Core, Watchdog, API Gateway, and Agent Manager. These are long-running deployments.
2. **Data Plane Namespace**: Contains the Databases (Postgres, Redis) and Telemetry stack.
3. **Execution Namespace**: A highly volatile namespace where Agent Manager spins up ephemeral Pods (Agent Sandboxes) to execute jobs.

## High Availability
- The Jarvis Core and Agent Manager are deployed with Multiple Replicas.
- If a node fails, Kubernetes automatically reschedules the pods.
- The Watchdog detects the pod death, updates the dashboard state to "Re-allocating", and the Agent Manager spins up a replacement agent.

## Dashboard Visibility
The Dashboard abstracts the Kubernetes complexity but provides an "Infrastructure Map".
- Visually shows the underlying cluster nodes and their resource utilization.
- Allows the owner to scale the cluster (e.g., clicking `[Add Node]`) directly from the UI if the system is starved for compute.
