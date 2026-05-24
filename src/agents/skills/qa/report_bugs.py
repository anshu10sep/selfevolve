def report_bugs(bug_description: str, steps_to_reproduce: list, severity: str, affected_component: str) -> dict:
    """
    Reports a newly discovered bug, including detailed steps to reproduce and severity.

    Args:
        bug_description: A clear description of the bug.
        steps_to_reproduce: A list of steps to consistently reproduce the bug.
        severity: The severity of the bug ("critical", "high", "medium", "low").
        affected_component: The system component where the bug was found.

    Returns:
        A dictionary confirming the bug report and providing a bug ID.
    """
    print(f"Reporting bug: '{bug_description[:100]}' in {affected_component} with severity {severity}.")
    bug_id = f"BUG-{hash(bug_description)}" # Simulate bug ID generation
    return {"status": "bug_reported", "bug_id": bug_id, "severity": severity, "affected_component": affected_component}
