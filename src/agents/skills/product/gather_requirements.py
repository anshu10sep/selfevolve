from agents.skills.validator import skill

@skill("product")
def gather_requirements(feature_name: str, stakeholders: list[str]) -> list[str]:
    """
    Gathers detailed requirements for a new feature from various stakeholders.

    Args:
        feature_name: The name of the feature for which to gather requirements.
        stakeholders: A list of stakeholders to consult (e.g., "trading_team", "compliance_officer").

    Returns:
        A list of detailed requirements.
    """
    print(f"Gathering requirements for feature '{feature_name}' from stakeholders: {stakeholders}")
    requirements = []
    if "trading_team" in stakeholders:
        requirements.append("Real-time data feed integration.")
    if "compliance_officer" in stakeholders:
        requirements.append("Audit trail for all transactions.")
    return requirements
