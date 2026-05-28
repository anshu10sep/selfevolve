"""
Hermes Vision Skill for Macro Analyst

Equips the Macro Analyst with Hermes multimodal vision capabilities
to parse charts, yield curves, dot plots, and other visual macro data.
"""

from __future__ import annotations

import logging

from agents.skills.jarvis.agent_messaging import _skill_registry
from integrations.hermes_client import hermes_client

logger = logging.getLogger("hermes_vision_skill")

async def analyze_chart_with_hermes(image_url: str, analysis_instructions: str = "") -> str:
    """
    Analyze a macro-economic chart or visual data using the Hermes Vision API.
    
    Use this tool when you are provided with an image URL representing visual data
    (e.g., Federal Reserve dot plots, yield curve graphs, inflation heatmaps)
    that cannot be analyzed purely as text.
    
    Args:
        image_url: The URL to the image file to analyze.
        analysis_instructions: Instructions on what specific signals to look for 
                               in the chart (e.g., "Determine if the yield curve is inverted").
                               
    Returns:
        A string containing the vision model's analysis of the chart.
    """
    logger.info(f"Macro Analyst requested vision analysis for: {image_url}")
    
    result = await hermes_client.analyze_image(
        image_url=image_url, 
        instructions=analysis_instructions
    )
    
    if result.get("success"):
        analysis = result.get("analysis", "")
        return analysis
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"Vision analysis failed for {image_url}: {error}")
        return f"Failed to analyze chart {image_url}. Error: {error}"


# Register the skill for the Macro Analyst
_skill_registry.register_skill(
    "macro_analyst",
    "analyze_chart_with_hermes",
    analyze_chart_with_hermes,
    description="Analyze a macro-economic chart or visual data using the Hermes Vision API. Ideal for dot plots, yield curves, and heatmaps."
)
