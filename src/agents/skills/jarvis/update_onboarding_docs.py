import os
from typing import Dict, List

def get_agent_structure(agents_dir: str) -> Dict[str, List[str]]:
    """
    Scans the agents directory and returns a dictionary mapping agent names to their skills.
    
    Args:
        agents_dir (str): Path to the agents directory.
        
    Returns:
        Dict[str, List[str]]: Dictionary of agents and their skills.
    """
    agent_structure = {}
    if not os.path.exists(agents_dir):
        return agent_structure
        
    for agent_name in os.listdir(agents_dir):
        agent_path = os.path.join(agents_dir, agent_name)
        if os.path.isdir(agent_path):
            skills = []
            for file_name in os.listdir(agent_path):
                if file_name.endswith('.py') and file_name != '__init__.py':
                    skills.append(file_name)
            if skills:
                agent_structure[agent_name] = sorted(skills)
                
    return agent_structure

def generate_onboarding_markdown(agent_structure: Dict[str, List[str]]) -> str:
    """
    Generates the markdown content for the agent onboarding documentation.
    
    Args:
        agent_structure (Dict[str, List[str]]): Dictionary of agents and their skills.
        
    Returns:
        str: Markdown content.
    """
    md_content = [
        "# SelfEvolve Agent Onboarding Documentation",
        "",
        "Welcome to the SelfEvolve autonomous trading system! This document outlines the current agent structure, their roles, and their respective skills.",
        "",
        "## Agent Roles and Skills",
        ""
    ]
    
    for agent, skills in sorted(agent_structure.items()):
        md_content.append(f"### {agent.replace('_', ' ').title()}")
        md_content.append(f"**Directory:** `agents/skills/{agent}/`")
        md_content.append("")
        md_content.append("#### Available Skills:")
        for skill in skills:
            md_content.append(f"- `{skill}`")
        md_content.append("")
        
    md_content.extend([
        "## How to Add a New Agent",
        "1. Create a new directory under `agents/skills/` with the agent's name.",
        "2. Add Python files (`.py`) for each skill the agent should possess.",
        "3. Ensure each skill has proper docstrings and type hints.",
        "4. Run the `update_onboarding_docs` skill to regenerate this documentation.",
        "",
        "## How to Add a New Skill",
        "1. Navigate to the specific agent's directory: `agents/skills/<agent_name>/`.",
        "2. Create a new Python file for the skill (e.g., `new_skill.py`).",
        "3. Implement the skill logic with clear docstrings.",
        "4. Run the `update_onboarding_docs` skill to update the documentation."
    ])
    
    return "\n".join(md_content)

def update_onboarding_docs(docs_file_path: str = "docs/agent_onboarding.md", agents_dir: str = "agents/skills") -> str:
    """
    Updates the agent onboarding documentation file based on the current directory structure.
    
    Args:
        docs_file_path (str): Path to the output markdown file.
        agents_dir (str): Path to the agents directory.
        
    Returns:
        str: Status message indicating success or failure.
    """
    try:
        # Ensure docs directory exists
        docs_dir = os.path.dirname(docs_file_path)
        if docs_dir:
            os.makedirs(docs_dir, exist_ok=True)
        
        agent_structure = get_agent_structure(agents_dir)
        if not agent_structure:
            return f"Error: No agents found in {agents_dir}"
            
        md_content = generate_onboarding_markdown(agent_structure)
        
        with open(docs_file_path, 'w') as f:
            f.write(md_content)
            
        return f"Successfully updated agent onboarding docs at {docs_file_path}"
    except Exception as e:
        return f"Failed to update onboarding docs: {str(e)}"

if __name__ == "__main__":
    # Example usage
    print(update_onboarding_docs())
