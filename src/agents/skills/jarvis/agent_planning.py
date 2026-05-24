import logging
import traceback
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def create_execution_plan(goal: str, available_agents: List[str]) -> Dict[str, Any]:
    """
    Create an execution plan for a given goal using available agents.
    
    Args:
        goal (str): The objective to achieve.
        available_agents (list): List of agent names available for tasks.
        
    Returns:
        dict: The structured execution plan.
    """
    try:
        logger.info(f"Creating execution plan for goal: {goal}")
        
        if not available_agents:
            raise ValueError("No agents available for planning.")
            
        plan = {
            "goal": goal,
            "steps": [
                {"step": 1, "agent": available_agents[0], "action": "Analyze requirements"},
                {"step": 2, "agent": available_agents[-1] if len(available_agents) > 1 else available_agents[0], "action": "Execute task"}
            ],
            "status": "planned"
        }
        return plan
        
    except Exception as e:
        logger.error(f"Error creating execution plan: {str(e)}")
        logger.debug(traceback.format_exc())
        return {
            "goal": goal,
            "status": "failed",
            "error": str(e)
        }