import os
import logging
from typing import Dict, Any
from agents.skills.jarvis.network_utils import robust_request

logger = logging.getLogger(__name__)

def generate_code(prompt: str, model: str = "gpt-4") -> str:
    """
    Generates code using an LLM based on the provided prompt.
    Includes robust retry logic for network stability.
    
    Args:
        prompt: The instruction or description for the code to generate.
        model: The LLM model to use.
        
    Returns:
        The generated code as a string.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system", 
                "content": "You are an expert Python developer. Output only valid Python code without markdown formatting if possible, or ensure it's well-structured."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        "temperature": 0.2
    }
    
    response = robust_request("POST", url, headers=headers, json=payload, timeout=60)
    response_data = response.json()
    
    try:
        content = response_data["choices"][0]["message"]["content"]
        # Strip markdown code blocks if present
        if content.startswith("```python"):
            content = content[9:]
        elif content.startswith("```"):
            content = content[3:]
            
        if content.endswith("```"):
            content = content[:-3]
            
        return content.strip()
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected response format from LLM: {response_data}")
        raise ValueError("Failed to parse code from LLM response") from e

def review_code(code: str, model: str = "gpt-4") -> str:
    """
    Reviews the provided code and suggests improvements.
    Includes robust retry logic for network stability.
    
    Args:
        code: The Python code to review.
        model: The LLM model to use.
        
    Returns:
        A string containing the review comments.
    """
    prompt = f"Please review the following Python code and suggest improvements for performance, security, and readability:\n\n{code}"
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")
        
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert Python code reviewer."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    response = robust_request("POST", url, headers=headers, json=payload, timeout=60)
    response_data = response.json()
    
    try:
        return response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected response format from LLM: {response_data}")
        raise ValueError("Failed to parse review from LLM response") from e