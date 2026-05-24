def incident_response(incident_report: dict) -> dict:
    """
    Initiates and manages the response to a detected security incident.

    Args:
        incident_report: A dictionary detailing the security incident (e.g., type, severity, affected systems).

    Returns:
        A dictionary outlining the immediate actions taken and a plan for resolution.
    """
    print(f"Responding to security incident: {incident_report.get('type', 'Unknown')} with severity {incident_report.get('severity', 'Low')}")
    if incident_report.get("severity") == "critical":
        actions = ["Isolate affected systems", "Notify relevant teams", "Begin forensic analysis"]
    else:
        actions = ["Investigate logs", "Assess impact"]
    return {"status": "response_initiated", "actions_taken": actions, "next_steps": "Detailed investigation and remediation."}
===