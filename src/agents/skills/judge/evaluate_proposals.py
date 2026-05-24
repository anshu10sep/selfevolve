def evaluate_proposals(proposals: list, criteria: dict) -> dict:
    """
    Evaluates a set of proposals against predefined criteria and provides a score or ranking.

    Args:
        proposals: A list of dictionaries, each representing a proposal.
        criteria: A dictionary defining the evaluation criteria and their weights.

    Returns:
        A dictionary containing the evaluation results, including scores and a ranked list of proposals.
    """
    print(f"Evaluating {len(proposals)} proposals against criteria: {list(criteria.keys())}")
    results = []
    for i, proposal in enumerate(proposals):
        score = 0
        feedback = []
        # Example evaluation logic
        if proposal.get("risk_level", "high") == "low":
            score += criteria.get("risk_aversion", 0.5) * 10
            feedback.append("Low risk profile.")
        if proposal.get("expected_return", 0) > 0.1:
            score += criteria.get("return_potential", 0.5) * 10
            feedback.append("High return potential.")
        results.append({"proposal_id": i + 1, "score": score, "feedback": feedback, "proposal": proposal})
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"evaluation_status": "completed", "ranked_proposals": results}
