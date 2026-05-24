import inspect
import functools
import logging
from typing import Callable, Any, Dict

logger = logging.getLogger(__name__)

class SkillValidationError(Exception):
    """Exception raised for errors in the skill validation process."""
    pass

class SkillRegistry:
    """Registry to keep track of all validated skills per agent."""
    _skills: Dict[str, Dict[str, Callable]] = {}

    @classmethod
    def register(cls, agent_name: str, name: str, func: Callable) -> None:
        """Registers a skill for a specific agent."""
        if agent_name not in cls._skills:
            cls._skills[agent_name] = {}
        cls._skills[agent_name][name] = func
        logger.debug(f"Registered skill '{name}' for agent '{agent_name}'")

    @classmethod
    def get_skills(cls, agent_name: str) -> Dict[str, Callable]:
        """Retrieves all skills for a specific agent."""
        return cls._skills.get(agent_name, {})

    @classmethod
    def get_all_skills(cls) -> Dict[str, Dict[str, Callable]]:
        """Retrieves all registered skills across all agents."""
        return cls._skills

    @classmethod
    def clear(cls) -> None:
        """Clears the registry (useful for testing)."""
        cls._skills = {}

def validate_skill_structure(func: Callable) -> None:
    """
    Validates that a skill function meets the required standards:
    - Must have a docstring.
    - All arguments must have type hints.
    - Must have a return type hint.
    """
    if not inspect.isfunction(func):
        raise SkillValidationError(f"Skill '{func.__name__}' must be a function.")

    # 1. Check docstring
    if not func.__doc__ or not func.__doc__.strip():
        raise SkillValidationError(
            f"Skill '{func.__name__}' must have a docstring describing its purpose, arguments, and return value."
        )
    
    sig = inspect.signature(func)
    
    # 2. Check argument type hints
    for name, param in sig.parameters.items():
        if param.annotation == inspect.Parameter.empty and name != 'self':
            raise SkillValidationError(
                f"Parameter '{name}' in skill '{func.__name__}' is missing a type hint."
            )
            
    # 3. Check return type hint
    if sig.return_annotation == inspect.Signature.empty:
        raise SkillValidationError(
            f"Skill '{func.__name__}' is missing a return type hint."
        )

def skill(agent_name: str) -> Callable:
    """
    Decorator to mark a function as an agent skill.
    Validates the skill structure and registers it in the SkillRegistry.
    
    Args:
        agent_name: The name of the agent this skill belongs to.
        
    Returns:
        The decorated function.
    """
    def decorator(func: Callable) -> Callable:
        # Validate the skill before registering
        validate_skill_structure(func)
        
        # Register the skill
        SkillRegistry.register(agent_name, func.__name__, func)
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)
            
        return wrapper
    return decorator