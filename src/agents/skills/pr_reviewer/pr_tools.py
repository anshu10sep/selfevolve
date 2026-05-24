def fetch_pr_details(pr_url: str) -> dict:
    """
    Fetches details of a pull request from a given URL.

    Args:
        pr_url: The URL of the pull request.

    Returns:
        A dictionary containing PR details like title, description, author, and changed files.
    """
    print(f"PR Reviewer: Fetching details for PR: {pr_url}")
    # Placeholder for actual GitHub API call
    return {
        "title": "Feature: Implement new trading strategy",
        "description": "This PR adds the XYZ trading strategy and associated tests.",
        "author": "dev_agent",
        "changed_files": ["src/strategies/xyz_strategy.py", "tests/test_xyz_strategy.py"],
        "status": "open"
    }

def add_pr_comment(pr_url: str, comment_text: str, file_path: str = None, line_number: int = None) -> dict:
    """
    Adds a comment to a pull request, optionally at a specific file and line.

    Args:
        pr_url: The URL of the pull request.
        comment_text: The text of the comment.
        file_path: (Optional) The path to the file to comment on.
        line_number: (Optional) The line number in the file to comment on.

    Returns:
        A dictionary indicating the status of the comment addition.
    """
    location = f" on {file_path}:{line_number}" if file_path and line_number else ""
    print(f"PR Reviewer: Adding comment to {pr_url}{location}: '{comment_text[:50]}...'")
    # Placeholder for actual GitHub API call
    return {"status": "comment_added", "comment": comment_text, "location": location}
===