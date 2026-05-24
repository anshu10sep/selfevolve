import os
import time
import socket
import logging
import requests
from typing import Dict, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)

def retry_on_network_error(max_retries=5, backoff_factor=2):
    """
    Decorator to retry LLM API calls on network errors, specifically handling
    socket.gaierror (Temporary failure in name resolution).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except (socket.gaierror, requests.exceptions.RequestException, ConnectionError) as e:
                    retries += 1
                    if retries >= max_retries:
                        logger.error(f"Max retries ({max_retries}) reached in CodeGenerator. Failed with error: {e}")
                        raise
                    sleep_time = backoff_factor ** retries
                    logger.warning(f"Network error in code generation: {e}. Retrying in {sleep_time} seconds... ({retries}/{max_retries})")
                    time.sleep(sleep_time)
        return wrapper
    return decorator

class CodeGenerator:
    """
    Skill for Jarvis to generate code using LLM APIs, robust against network errors
    like temporary failure in name resolution (socket.gaierror).
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"

    @retry_on_network_error(max_retries=5, backoff_factor=2)
    def generate_code(self, prompt: str, model: str = "gpt-4") -> str:
        """Generate code based on a prompt."""
        if not self.api_key:
            logger.warning("No API key provided for code generation.")
            return "# Error: No API key provided."
            
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are an expert Python developer for the SelfEvolve autonomous trading system."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

def generate_code(prompt: str, model: str = "gpt-4") -> str:
    """Helper function to generate code."""
    generator = CodeGenerator()
    return generator.generate_code(prompt, model)