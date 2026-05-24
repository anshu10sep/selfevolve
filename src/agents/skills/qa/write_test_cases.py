def write_test_cases(feature_requirements: list, test_type: str) -> list:
    """
    Writes detailed test cases based on feature requirements for a specific test type (e.g., functional, performance).

    Args:
        feature_requirements: A list of requirements for the feature to be tested.
        test_type: The type of tests to write (e.g., "functional", "integration", "performance").

    Returns:
        A list of dictionaries, each representing a test case with steps, expected results, and preconditions.
    """
    print(f"Writing {test_type} test cases for requirements: {feature_requirements}")
    test_cases = []
    for req in feature_requirements:
        test_cases.append({
            "test_id": f"TC-{hash(req)}",
            "description": f"Verify {req}",
            "steps": [f"Precondition: ...", f"Action: {req}", "Expected Result: ..."],
            "expected_result": "Functionality works as expected.",
            "type": test_type
        })
    return test_cases
===