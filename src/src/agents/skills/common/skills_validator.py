import os
import importlib.util
import sys
import shutil
from typing import List, Dict, Any

# PROJECT_ROOT is explicitly given in the prompt
PROJECT_ROOT = "/home/agentx/self-evolving/src"
SKILLS_BASE_DIR = os.path.join(PROJECT_ROOT, "agents", "skills")

class SkillValidationError(Exception):
    """Custom exception for skill validation errors."""
    pass

def _get_skill_path(agent_name: str, skill_file_name: str) -> str:
    """
    Constructs the absolute path to a skill file for a given agent.

    Args:
        agent_name (str): The name of the agent (e.g., "jarvis").
        skill_file_name (str): The name of the skill file (e.g., "system_audit.py").

    Returns:
        str: The absolute path to the skill file.
    """
    skill_dir = os.path.join(SKILLS_BASE_DIR, agent_name)
    skill_path = os.path.join(skill_dir, skill_file_name)
    return skill_path

def validate_skill_file(agent_name: str, skill_file_name: str) -> bool:
    """
    Validates a single skill file for a given agent.

    Checks:
    1. If the skill file exists at the expected path.
    2. If the skill file is indeed a file (not a directory).
    3. If the skill file is a valid Python module (can be imported without syntax errors
       or unhandled exceptions during module loading).

    Args:
        agent_name (str): The name of the agent (e.g., "jarvis").
        skill_file_name (str): The name of the skill file (e.g., "system_audit.py").

    Returns:
        bool: True if the skill file is valid.

    Raises:
        SkillValidationError: If the skill file does not exist, is not a file, or cannot be imported.
    """
    skill_path = _get_skill_path(agent_name, skill_file_name)

    if not os.path.exists(skill_path):
        raise SkillValidationError(
            f"Skill file '{skill_file_name}' for agent '{agent_name}' not found at '{skill_path}'."
        )
    if not os.path.isfile(skill_path):
        raise SkillValidationError(
            f"Skill path '{skill_path}' for agent '{agent_name}' is not a file."
        )

    # Attempt to import the module to check for syntax errors and basic importability.
    # We create a unique module name to avoid conflicts if multiple skills have the same base name
    # or if the same skill is loaded for different agents in a complex scenario.
    module_name = f"selfevolve.agents.skills.{agent_name}.{os.path.splitext(skill_file_name)[0]}"
    
    # Use importlib.util to load the module without adding it to sys.modules permanently,
    # which is suitable for validation purposes to avoid side effects.
    spec = importlib.util.spec_from_file_location(module_name, skill_path)

    if spec is None:
        raise SkillValidationError(
            f"Could not create module spec for skill '{skill_file_name}' for agent '{agent_name}' at '{skill_path}'. "
            "This might indicate a problem with the file path, permissions, or a malformed Python file."
        )

    try:
        module = importlib.util.module_from_spec(spec)
        # Execute the module's code. This will raise an exception if there are syntax errors
        # or unhandled runtime errors during module loading (e.g., NameError, ImportError).
        spec.loader.exec_module(module)
        
        # Optional: Further validation can be added here, e.g., checking for specific functions
        # or classes that the agent expects the skill to expose.
        # Example:
        # if not hasattr(module, 'execute_skill_function'):
        #     raise SkillValidationError(
        #         f"Skill '{skill_file_name}' for agent '{agent_name}' lacks the required 'execute_skill_function'."
        #     )

    except Exception as e:
        # Catch any exception during module execution (e.g., SyntaxError, ImportError, NameError, etc.)
        raise SkillValidationError(
            f"Error importing or executing skill '{skill_file_name}' for agent '{agent_name}' "
            f"from '{skill_path}': {type(e).__name__}: {e}"
        ) from e

    return True

def validate_agent_skills(agent_name: str, skill_list: List[str]) -> Dict[str, bool]:
    """
    Validates a list of skill files for a given agent.

    This function attempts to validate all provided skills and collects all errors
    before raising a single `SkillValidationError` if any issues are found.

    Args:
        agent_name (str): The name of the agent (e.g., "jarvis").
        skill_list (List[str]): A list of skill file names (e.g., ["system_audit.py", "github_ops.py"]).

    Returns:
        Dict[str, bool]: A dictionary where keys are skill file names and values are True if valid,
                        False if invalid. This dictionary is returned only if all skills are valid.

    Raises:
        SkillValidationError: If one or more skills fail validation. The exception message will
                              aggregate all validation errors found for better debugging.
    """
    validation_results = {}
    errors = []

    for skill_file_name in skill_list:
        try:
            validate_skill_file(agent_name, skill_file_name)
            validation_results[skill_file_name] = True
        except SkillValidationError as e:
            validation_results[skill_file_name] = False
            errors.append(str(e))
        except Exception as e: # Catch any other unexpected errors during validation
            validation_results[skill_file_name] = False
            errors.append(f"Unexpected error validating skill '{skill_file_name}' for agent '{agent_name}': {type(e).__name__}: {e}")

    if errors:
        raise SkillValidationError(
            f"Validation failed for agent '{agent_name}'. Found {len(errors)} error(s):\n" + "\n".join(errors)
        )

    return validation_results

# --- Example Usage and Test Setup ---
if __name__ == "__main__":
    print(f"Running skill validation example from: {os.getcwd()}")
    print(f"Assuming PROJECT_ROOT: {PROJECT_ROOT}")
    print(f"Skills base directory: {SKILLS_BASE_DIR}")

    # Define agents and their skills based on the prompt and for testing various scenarios
    agents_to_test = {
        "jarvis": ["system_audit.py", "github_ops.py", "agent_planning.py", "code_generation.py"],
        "pr_reviewer": ["code_review.py", "presubmit.py", "review_pipeline.py", "pr_tools.py"],
        "developer": ["new_dev_skill.py", "invalid_dev_skill.py", "non_existent_skill_for_dev.py"],
        "non_existent_agent": ["some_skill.py"] # For testing an agent directory that doesn't exist
    }

    # --- Setup: Create dummy skill files and directories for testing ---
    created_dirs = []
    created_files = []

    def create_dummy_skill_file(agent_name, skill_file_name, content="""
def execute():
    """A dummy skill function."""
    return f'Skill {skill_file_name} executed for {agent_name}!'
"""):
        """Helper to create a dummy skill file."""
        agent_skill_dir = os.path.join(SKILLS_BASE_DIR, agent_name)
        os.makedirs(agent_skill_dir, exist_ok=True)
        if agent_skill_dir not in created_dirs:
            created_dirs.append(agent_skill_dir)
        
        skill_path = os.path.join(agent_skill_dir, skill_file_name)
        with open(skill_path, "w") as f:
            f.write(content)
        created_files.append(skill_path)
        print(f"Created dummy skill: {skill_path}")

    print("\n--- Setting up dummy skill files for testing ---")
    for agent, skills in agents_to_test.items():
        if agent == "non_existent_agent": # Don't create directory for this to test path non-existence
            continue
        for skill in skills:
            if skill == "invalid_dev_skill.py":
                create_dummy_skill_file(agent, skill, "def invalid_syntax: pass # This has a syntax error")
            elif skill == "non_existent_skill_for_dev.py":
                # This one will not be created, to test file non-existence
                pass
            elif skill == "some_skill.py": # This is for non_existent_agent, so it won't be created here
                pass
            else:
                create_dummy_skill_file(agent, skill)

    # --- Run Validation Tests ---
    print("\n--- Running Skill Validation Tests ---")

    # Test 1: Valid Jarvis skills (expected success)
    print("\n--- Validating Jarvis skills (expected success) ---")
    try:
        results = validate_agent_skills("jarvis", agents_to_test["jarvis"])
        print(f"Jarvis skills validation successful: {results}")
    except SkillValidationError as e:
        print(f"Jarvis skills validation FAILED unexpectedly: {e}")

    # Test 2: Valid PR Reviewer skills (expected success)
    print("\n--- Validating PR Reviewer skills (expected success) ---")
    try:
        results = validate_agent_skills("pr_reviewer", agents_to_test["pr_reviewer"])
        print(f"PR Reviewer skills validation successful: {results}")
    except SkillValidationError as e:
        print(f"PR Reviewer skills validation FAILED unexpectedly: {e}")

    # Test 3: Developer skills with one invalid and one non-existent (expected failure with multiple errors)
    print("\n--- Validating Developer skills (expected failure with multiple errors) ---")
    try:
        results = validate_agent_skills("developer", agents_to_test["developer"])
        print(f"Developer skills validation successful (UNEXPECTED): {results}")
    except SkillValidationError as e:
        print(f"Developer skills validation FAILED as expected:\n{e}")

    # Test 4: Agent directory does not exist (expected failure for skill file not found)
    print("\n--- Validating Non-Existent Agent skills (expected failure) ---")
    try:
        results = validate_agent_skills("non_existent_agent", agents_to_test["non_existent_agent"])
        print(f"Non-Existent Agent skills validation successful (UNEXPECTED): {results}")
    except SkillValidationError as e:
        print(f"Non-Existent Agent skills validation FAILED as expected:\n{e}")

    # --- Cleanup ---
    print("\n--- Cleaning up dummy skill files and directories ---")
    for f_path in created_files:
        if os.path.exists(f_path):
            os.remove(f_path)
            print(f"Removed dummy file: {f_path}")
    
    # Remove directories, but only if they are empty after file removal
    # Sort in reverse order to delete child directories before parents
    for d_path in sorted(list(set(created_dirs)), reverse=True):
        if os.path.exists(d_path):
            try:
                os.rmdir(d_path)
                print(f"Removed empty dummy directory: {d_path}")
            except OSError as e:
                print(f"Could not remove directory {d_path} (might not be empty or permissions issue): {e}")
===