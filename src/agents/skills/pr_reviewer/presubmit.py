def run_linters(file_content: str, file_path: str, linter_config: dict) -> list:
    """
    Runs static code analysis tools (linters) on the provided file content.

    Args:
        file_content: The content of the code file as a string.
        file_path: The path to the file being linted.
        linter_config: A dictionary of linter configurations (e.g., rules, exclusions).

    Returns:
        A list of linter warnings or errors.
    """
    print(f"PR Reviewer: Running linters on {file_path}")
    warnings = []
    if "  " in file_content: # Simple check for inconsistent indentation
        warnings.append("Inconsistent indentation detected (spaces).")
    if len(file_content.splitlines()) > linter_config.get("max_lines_per_file", 500):
        warnings.append(f"File exceeds max lines ({linter_config.get('max_lines_per_file')}).")
    return warnings

def execute_unit_tests(test_file_content: str, test_file_path: str) -> dict:
    """
    Executes unit tests associated with the changes in a pull request.

    Args:
        test_file_content: The content of the test file as a string.
        test_file_path: The path to the test file.

    Returns:
        A dictionary summarizing the test results (pass/fail, coverage).
    """
    print(f"PR Reviewer: Executing unit tests from {test_file_path}")
    # Simulate test execution
    if "assert False" in test_file_content:
        return {"status": "failed", "failures": 1, "coverage": "75%", "error_message": "Assertion failed in test_example."}
    return {"status": "passed", "failures": 0, "coverage": "90%"}
===