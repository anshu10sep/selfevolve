from agents.skills.validator import skill

@skill("product")
def define_features(user_story: str, business_value: str) -> dict:
    """
    Defines new product features based on user stories and their associated business value.

    Args:
        user_story: A description of the user's need or desired functionality.
        business_value: The expected business value of implementing this feature.

    Returns:
        A dictionary containing the defined feature's name, description, and initial requirements.
    """
    print(f"Defining feature for user story: {user_story[:100]}...")
    feature_name = f"Implement {user_story.split(' ')[0]} functionality"
    requirements = [f"As a user, I want to {user_story.lower().replace('as a user, i want to ', '')}", "Acceptance criteria: ..."]
    return {"feature_name": feature_name, "description": user_story, "business_value": business_value, "initial_requirements": requirements}
