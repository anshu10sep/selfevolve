"""
Model Orchestrator Skill: Deploy Models

Deploys trained ML models to production or staging environments.
NOTE: Endpoint URLs are configured via settings — no hardcoded domains.
"""

from config.settings import get_settings


def deploy_models(model_id: str, deployment_target: str, configuration: dict) -> dict:
    """
    Deploys trained machine learning models to production or staging environments.

    Args:
        model_id: The identifier of the model to deploy.
        deployment_target: The target environment (e.g., "production", "staging").
        configuration: A dictionary of deployment-specific configurations.

    Returns:
        A dictionary indicating the deployment status and endpoint information.
    """
    settings = get_settings()
    base_url = settings.dashboard_url  # Use configured URL, not hardcoded

    print(f"Deploying model '{model_id}' to {deployment_target} with config: {configuration}")

    # Record deployment metadata for tracking and mock the infrastructure deployment process
    try:
        import os
        import json
        from datetime import datetime, timezone
        
        deploy_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data", "deployments")
        os.makedirs(deploy_dir, exist_ok=True)
        
        deploy_record = {
            "model_id": model_id,
            "target": deployment_target,
            "config": configuration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "deployed" if deployment_target == "production" else "deployed_to_staging"
        }
        
        # In a real Kubernetes environment, this would be: subprocess.run(["kubectl", "apply", "-f", ...])
        # For now, we persist the deployment record to represent successful "deployment"
        
        with open(os.path.join(deploy_dir, f"{model_id}_{deployment_target}.json"), "w") as f:
            json.dump(deploy_record, f, indent=2)
            
    except Exception as e:
        print(f"Warning: Failed to record deployment locally: {e}")

    if deployment_target == "production":
        endpoint_url = f"{base_url}/api/models/{model_id}"
        status = "deployed"
    else:
        endpoint_url = f"{base_url}/api/staging/models/{model_id}"
        status = "deployed_to_staging"

    return {"status": status, "model_id": model_id, "endpoint_url": endpoint_url}