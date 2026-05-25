"""
Agent Loader — Dynamic Runtime Agent Loading

Provides the ability to dynamically load agent modules from Python files,
instantiate them, and register them in the agent_messaging registry.

This is the missing link between create_new_agent_file() (which writes .py
files to disk) and actually running those agents.

Usage:
    from evolution.agent_loader import load_and_start_agent
    result = load_and_start_agent("/path/to/new_agent.py")
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import inspect
from typing import Optional, Type

import structlog

logger = structlog.get_logger(component="agent_loader")


def load_agent_from_file(filepath: str) -> Optional[object]:
    """
    Dynamically import a Python module from a file path, find the BaseAgent
    subclass, instantiate it with an LLM, and return the agent instance.

    Args:
        filepath: Absolute path to the agent Python file.

    Returns:
        An instantiated agent, or None if loading failed.
    """
    from agents.base_agent import BaseAgent
    from core.llm_factory import get_efficient_llm

    if not os.path.exists(filepath):
        logger.error("agent_file_not_found", filepath=filepath)
        return None

    if not filepath.endswith(".py"):
        logger.error("agent_file_not_python", filepath=filepath)
        return None

    # Generate a unique module name from the filepath
    module_name = os.path.splitext(os.path.basename(filepath))[0]
    # Prefix to avoid collisions
    full_module_name = f"agents.dynamic.{module_name}"

    try:
        # Load the module spec from file
        spec = importlib.util.spec_from_file_location(full_module_name, filepath)
        if spec is None or spec.loader is None:
            logger.error("agent_spec_failed", filepath=filepath)
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[full_module_name] = module
        spec.loader.exec_module(module)

        # Find the BaseAgent subclass in the module
        agent_class: Optional[Type[BaseAgent]] = None
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseAgent) and obj is not BaseAgent:
                agent_class = obj
                break

        if agent_class is None:
            logger.error("no_agent_class_found", filepath=filepath, module=full_module_name)
            return None

        # Instantiate with an LLM
        llm = get_efficient_llm()
        agent = agent_class(llm=llm)

        logger.info(
            "agent_loaded",
            filepath=filepath,
            class_name=agent_class.__name__,
            agent_name=agent.name,
        )

        return agent

    except Exception as e:
        logger.error("agent_load_failed", filepath=filepath, error=str(e))
        return None


def load_and_start_agent(filepath: str) -> dict:
    """
    Load an agent from a Python file, instantiate it, and register it in
    the agent_messaging registry so it's visible to list_all_agents and
    can receive delegated tasks.

    Args:
        filepath: Absolute path to the agent Python file.

    Returns:
        Dict with status, agent_name, and any error message.
    """
    from agents.skills.jarvis.agent_messaging import register_agent_instance

    agent = load_agent_from_file(filepath)
    if agent is None:
        return {
            "status": "FAILED",
            "error": f"Could not load agent from {filepath}",
        }

    # Register with multiple keys for lookup flexibility
    agent_name = getattr(agent, "name", "unknown")
    agent_key = agent_name.lower().replace(" ", "_")

    register_agent_instance(agent_key, agent)
    register_agent_instance(agent_name.lower(), agent)

    logger.info(
        "agent_started",
        agent_name=agent_name,
        registry_key=agent_key,
        filepath=filepath,
    )

    return {
        "status": "SUCCESS",
        "agent_name": agent_name,
        "registry_key": agent_key,
        "filepath": filepath,
    }
