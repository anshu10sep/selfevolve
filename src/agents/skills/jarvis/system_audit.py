def perform_system_health_check() -> dict:
    """
    Performs a comprehensive health check of the entire trading system.

    Returns:
        A dictionary containing the health status of various system components.
    """
    print("Jarvis: Performing system health check...")
    # Placeholder for actual system monitoring and status aggregation
    health_status = {
        "database": {"status": "healthy", "latency_ms": 10},
        "api_gateway": {"status": "healthy", "uptime_percent": 99.9},
        "trading_engine": {"status": "healthy", "last_trade_ms_ago": 500},
        "data_feed": {"status": "healthy", "last_update_ms_ago": 100},
        "agent_orchestrator": {"status": "healthy", "active_agents": 20}
    }
    overall_status = "healthy"
    for component, status_info in health_status.items():
        if status_info["status"] != "healthy":
            overall_status = "degraded"
            break
    return {"overall_status": overall_status, "components": health_status}

def get_agent_status(agent_name: str = None) -> dict:
    """
    Retrieves the current operational status of all or a specific agent.

    Args:
        agent_name: (Optional) The name of a specific agent to query. If None, returns status for all agents.

    Returns:
        A dictionary containing the status of the requested agent(s).
    """
    print(f"Jarvis: Getting status for agent: {agent_name if agent_name else 'all'}")
    # Placeholder for actual agent status monitoring
    all_agent_statuses = {
        "jarvis": {"status": "active", "last_task_completed": "system_audit"},
        "developer": {"status": "idle", "last_task_completed": "code_review"},
        "pr_reviewer": {"status": "active", "current_task": "review_pr_123"},
        "bull": {"status": "active", "current_task": "identify_bullish_signals"},
        "bear": {"status": "idle", "last_task_completed": "risk_assessment"},
    }
    if agent_name:
        return {agent_name: all_agent_statuses.get(agent_name, {"status": "unknown", "message": "Agent not found"})}
    return all_agent_statuses
===