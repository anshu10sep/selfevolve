from typing import Callable, Dict, Optional

class SkillRegistry:
    """
    Central registry for all validated skills in the SelfEvolve system.
    Agents can query this registry to find available tools.
    """
    _skills: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, func: Callable) -> None:
        """
        Registers a validated skill.
        
        Args:
            func (Callable): The skill function to register.
        """
        # Use the fully qualified name (e.g., agents.skills.auditor.compliance_check.verify_trade_compliance)
        name = f"{func.__module__}.{func.__name__}"
        cls._skills[name] = func
        
    @classmethod
    def get_skill(cls, name: str) -> Optional[Callable]:
        """
        Retrieves a skill by its fully qualified name.
        
        Args:
            name (str): The fully qualified name of the skill.
            
        Returns:
            Optional[Callable]: The skill function if found, None otherwise.
        """
        return cls._skills.get(name)
        
    @classmethod
    def get_all_skills(cls) -> Dict[str, Callable]:
        """
        Returns all registered skills.
        
        Returns:
            Dict[str, Callable]: A dictionary of all registered skills.
        """
        return cls._skills.copy()
        
    @classmethod
    def clear(cls) -> None:
        """Clears the registry (useful for testing)."""
        cls._skills.clear()
