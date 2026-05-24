def initiate_review_pipeline(pr_url: str) -> dict:
    """
    Initiates the full PR review pipeline, orchestrating various review steps.

    Args:
        pr_url: The URL of the pull request to review.

    Returns:
        A dictionary summarizing the initiation status and next steps.
    """
    print(f"PR Reviewer: Initiating review pipeline for PR: {pr_url}")
    # This function would call other skills like fetch_pr_details, run_linters, review_code_quality, etc.
    return {"status": "pipeline_initiated", "pr_url": pr_url, "next_steps": ["fetch_details", "run_presubmit_checks", "perform_code_review"]}

def summarize_review_findings(pr_url: str, review_results: list) -> dict:
    """
    Aggregates and summarizes all findings from the PR review process.

    Args:
        pr_url: The URL of the pull request.
        review_results: A list of dictionaries, each containing results from a specific review step.

    Returns:
        A comprehensive summary of the review, including overall status and recommendations.
    """
    print(f"PR Reviewer: Summarizing review findings for PR: {pr_url}")
    overall_status = "approved"
    comments_count = 0
    for result in review_results:
        if result.get("status") == "failed" or (result.get("comments") and len(result["comments"]) > 0) or (result.get("bugs") and len(result["bugs"]) > 0):
            overall_status = "changes_requested"
        comments_count += len(result.get("comments", [])) + len(result.get("bugs", []))
    
    recommendation = "Approve" if overall_status == "approved" else "Request changes"
    return {"overall_status": overall_status, "total_comments": comments_count, "recommendation": recommendation}
