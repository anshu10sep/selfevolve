def make_final_decision(options: list, evaluation_results: dict, risk_tolerance: str) -> dict:
    """
    Makes a final, binding decision based on evaluated options, considering risk tolerance.

    Args:
        options: A list of available options.
        evaluation_results: The results from an evaluation skill, typically including scores.
        risk_tolerance: The system's current risk tolerance ("low", "medium", "high").

    Returns:
        A dictionary specifying the chosen option and the rationale.
    """
    print(f"Making final decision from {len(options)} options with risk tolerance: {risk_tolerance}")
    if not evaluation_results or not evaluation_results.get("ranked_proposals"):
        return {"decision_status": "failed", "reason": "No valid evaluation results provided."}

    best_option = evaluation_results["ranked_proposals"][0]
    rationale = f"Selected the highest-scoring proposal (ID: {best_option['proposal_id']}) with a score of {best_option['score']}."

    # Add risk tolerance consideration
    if risk_tolerance == "low" and best_option["proposal"].get("risk_level", "high") == "high":
        # Try to find a lower risk option if available and score is close
        for opt in evaluation_results["ranked_proposals"]:
            if opt["proposal"].get("risk_level") == "low" and opt["score"] > (best_option["score"] * 0.8): # within 20% of best
                best_option = opt
                rationale = f"Selected a lower-risk proposal (ID: {best_option['proposal_id']}) due to low risk tolerance, despite slightly lower score."
                break

    return {"decision_status": "made", "chosen_option": best_option["proposal"], "rationale": rationale}
===