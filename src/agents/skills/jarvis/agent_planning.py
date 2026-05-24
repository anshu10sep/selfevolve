import os
import json
import logging
from typing import Dict, Any, List
from agents.skills.jarvis.network_utils import robust_request

logger = logging.getLogger(__name__)

def generate_plan(goal: str, context: str = "") -> List[Dict[str, Any]]:
    """
    Generates a step-by-step plan to achieve a specific goal using an LLM.
    Includes robust retry logic for network stability.
    
    Args:
        goal: The objective to achieve.
        context: Additional context or constraints.
        
    Returns:
        A list of steps, where each step is a dictionary with 'step' and 'description'.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    system_prompt = (
        "You are an AI agent planner. Break down the user's goal into a logical sequence of actionable steps. "
        "Output ONLY a valid JSON array of objects, where each object has a 'step' (integer) and 'description' (string) key."
    )
    
    user_prompt = f"Goal: {goal}\nContext: {context}"
    
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }
    
    response = robust_request("POST", url, headers=headers, json=payload, timeout=60)
    response_data = response.json()
    
    try:
        content = response_data["choices"][0]["message"]["content"]
        # Clean up potential markdown formatting
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
            
        if content.endswith("```"):
            content = content[:-3]
            
        plan = json.loads(content.strip())
        return plan
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        logger.error(f"Failed to parse plan from LLM response: {response_data}")
        raise ValueError("Failed to generate a valid plan format") from e