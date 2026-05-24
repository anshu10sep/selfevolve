import inspect
from typing import Callable, Any

class SkillValidationError(Exception):
    """Exception raised when a skill fails validation."""
    pass

class SkillValidator:
    """
    Validates skills to ensure they meet the SelfEvolve system requirements.
    A valid skill must:
    1. Be a callable (function or method).
    2. Have a non-empty docstring (so the LLM knows what it does).
    3. Have type hints for all parameters (so the LLM knows what to pass).
    4. Have a return type hint (so the LLM knows what to expect).
    """
    
    @staticmethod
    def validate(func: Callable) -> bool:
        """
        Validates a skill function.
        
        Args:
            func (Callable): The function to validate.
            
        Returns:
            bool: True if the skill is valid.
            
        Raises:
            SkillValidationError: If the skill fails validation.
        """
        if not callable(func):
            raise SkillValidationError(f"Skill '{getattr(func, '__name__', str(func))}' is not callable.")
            
        name = func.__name__
        
        # 1. Check docstring
        if not func.__doc__ or not func.__doc__.strip():
            raise SkillValidationError(f"Skill '{name}' is missing a docstring. All skills must be documented.")
            
        # 2. Check type hints for parameters and return type
        try:
            sig = inspect.signature(func)
        except ValueError:
            raise SkillValidationError(f"Skill '{name}' does not have a valid signature.")
            
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            if param.annotation == inspect.Parameter.empty:
                raise SkillValidationError(f"Skill '{name}' is missing a type hint for parameter '{param_name}'.")
                
        if sig.return_annotation == inspect.Signature.empty:
            raise SkillValidationError(f"Skill '{name}' is missing a return type hint.")
            
        return True

def skill(func: Callable) -> Callable:
    """
    Decorator to mark a function as a skill, validate it, and register it.
    
    Args:
        func (Callable): The function to decorate.
        
    Returns:
        Callable: The decorated function.
    """
    # Validate the skill structure at import time
    SkillValidator.validate(func)
    func.__is_skill__ = True
    
    # Register the skill in the global registry
    from agents.skills.registry import SkillRegistry
    SkillRegistry.register(func)
    
    return func
