# Code Repository Integration

For Jarvis to be a useful software engineering system, it must integrate deeply with version control systems (e.g., GitHub, GitLab).

## The Integration Layer

The system uses a centralized Integration Service rather than letting individual agents manage API tokens.

### Features
- **Webhook Listener**: Listens for external events. (e.g., A human developer merges a PR, triggering Jarvis to evaluate the new `main` branch).
- **Token Management**: Securely stores OAuth tokens or GitHub App private keys. Agents request temporary, scoped access tokens when they need to push code.
- **Repository Cloning**: Maintains a localized, highly-available cache of the target repository to speed up agent sandbox provisioning.

## Dashboard Visualization
On the dashboard, the "Repository Integration" node shows:
- Current rate-limit status with GitHub.
- List of active webhooks and their health (e.g., 200 OK vs 500 errors).
- The sync status of the localized repository cache.

## Owner Drilldown
The owner can click into this component to manually trigger a repository sync or rotate API keys without needing to restart the entire system or touch environment variables.
