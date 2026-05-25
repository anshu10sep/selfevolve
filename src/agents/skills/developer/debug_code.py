from agents.skills.validator import skill

@skill("developer")
def debug_code(file_path: str, error_message: str) -> str:
    """
    Analyzes code to identify and fix bugs based on error messages or reported issues.

    Args:
        file_path: The path to the file containing the code to debug.
        error_message: The error message or description of the bug.

    Returns:
        A string describing the proposed fix or the debugged code snippet.
    """
    print(f"Debugging code in {file_path} due to error: {error_message}")
    # Placeholder for actual debugging logic
    if "IndexError" in error_message:
        return "Consider adding boundary checks to list access."
    return "Investigating the root cause of the error."
