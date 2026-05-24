"""
LLM Factory

Centralized LLM instantiation for the entire system.
Currently locked to Gemini 3.1 Pro across all tiers.
Future: Model Optimizer Agent will dynamically switch models
per agent based on performance metrics once subscriptions are active.
"""

from __future__ import annotations

from typing import Optional

import structlog
from langchain_core.language_models import BaseChatModel

from config.settings import get_settings

logger = structlog.get_logger(component="llm_factory")


def get_efficient_llm() -> BaseChatModel:
    """
    Get the cost-efficient LLM for triage, parsing, and analyst tasks.
    
    Currently: Gemini 3.1 Pro (all tiers locked until multi-model subs)
    """
    settings = get_settings()
    return _create_gemini_model(settings.efficient_model, temperature=0.3)


def get_premium_llm() -> BaseChatModel:
    """
    Get the premium LLM for Judge, debate, and evolution tasks.
    
    Currently: Gemini 3.1 Pro (all tiers locked until multi-model subs)
    """
    settings = get_settings()
    return _create_gemini_model(settings.premium_model, temperature=0.1)


def get_llm_by_name(model_name: str, temperature: float = 0.2) -> BaseChatModel:
    """
    Get an LLM by model name. Supports Gemini, OpenAI, and Anthropic.
    
    Used by the future Model Optimizer Agent to experiment with
    different models across agents.
    """
    if model_name.startswith("gemini"):
        return _create_gemini_model(model_name, temperature)
    elif model_name.startswith("gpt"):
        return _create_openai_model(model_name, temperature)
    elif model_name.startswith("claude"):
        return _create_anthropic_model(model_name, temperature)
    else:
        logger.warning(
            "unknown_model_prefix_defaulting_to_gemini",
            model=model_name,
        )
        return _create_gemini_model("gemini-3.1-pro", temperature)


def _create_gemini_model(
    model_name: str, temperature: float = 0.2
) -> BaseChatModel:
    """Create a Google Gemini chat model."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()

    if not settings.gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY not set. Please set it in .env file."
        )

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        max_output_tokens=2048,
        convert_system_message_to_human=True,
    )

    logger.info("llm_created", provider="gemini", model=model_name)
    return llm


def _create_openai_model(
    model_name: str, temperature: float = 0.2
) -> BaseChatModel:
    """Create an OpenAI chat model (Phase 2+)."""
    try:
        from langchain_openai import ChatOpenAI

        settings = get_settings()
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set.")

        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
            max_tokens=2048,
        )
    except ImportError:
        raise ImportError(
            "langchain-openai not installed. "
            "Run: pip install langchain-openai"
        )


def _create_anthropic_model(
    model_name: str, temperature: float = 0.2
) -> BaseChatModel:
    """Create an Anthropic chat model (Phase 2+)."""
    try:
        from langchain_anthropic import ChatAnthropic

        settings = get_settings()
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not set.")

        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=2048,
        )
    except ImportError:
        raise ImportError(
            "langchain-anthropic not installed. "
            "Run: pip install langchain-anthropic"
        )
