import os
import importlib.util
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def discover_and_validate_skills(skills_dir: str) -> bool:
    """
    Discovers all python files in the skills directory and its subdirectories,
    imports them to trigger the @skill decorator validation.
    """
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        logger.error(f"Skills directory {skills_dir} does not exist.")
        return False

    success = True
    skill_files_count = 0

    for py_file in skills_path.rglob("*.py"):
        if py_file.name in ("__init__.py", "validator.py", "validate_all.py"):
            continue

        module_name = py_file.stem
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec and spec.loader:
            try:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                skill_files_count += 1
                logger.info(f"Successfully validated skills in {py_file.relative_to(skills_path)}")
            except Exception as e:
                logger.error(f"Validation failed for {py_file.relative_to(skills_path)}: {str(e)}")
                success = False

    from agents.skills.validator import SkillRegistry
    total_skills = sum(len(skills) for skills in SkillRegistry.get_all_skills().values())
    
    if success:
        logger.info(f"Validation complete. {total_skills} skills validated across {skill_files_count} files.")
    else:
        logger.error("Validation failed. See errors above.")
        
    return success

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Ensure the src directory is in the python path
    src_dir = os.path.abspath(os.path.join(current_dir, "../../"))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
        
    success = discover_and_validate_skills(current_dir)
    sys.exit(0 if success else 1)