# Security and Authentication

Given that the Jarvis system has write access to production codebases and can execute arbitrary code in sandboxes, security is paramount.

## Authentication Layers

### 1. Owner Authentication
- The Dashboard requires Multi-Factor Authentication (MFA) or SSO (Single Sign-On) via Google/GitHub to access.

### 2. Service-to-Service Authentication
- Internal microservices communicate using mTLS (Mutual TLS). This ensures that a compromised sandbox cannot spoof requests to the Agent Manager.

## Security Boundaries
- **Network Segmentation**: Agent execution sandboxes run in a private subnet with no inbound internet access and highly restricted outbound access (via NAT Gateway + DNS Firewall).
- **Least Privilege**: The GitHub API token provided to the Integration Service is scoped only to the specific repositories Jarvis is allowed to touch.

## Dashboard Auditing
The dashboard contains a "Security Center" view:
- Lists all active Owner sessions.
- Displays a real-time audit log of who (or which agent) performed which action.
- Alerts on suspicious activity (e.g., an agent trying to SSH into a random IP address).
