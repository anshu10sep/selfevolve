"""
Hermes Browser Skill for Fundamental Analyst

Equips the Fundamental Analyst with headless Playwright capabilities 
via the Hermes Agent to extract unstructured real-time data from 
websites like SEC EDGAR, investor relations pages, and press releases.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from agents.skills.jarvis.agent_messaging import _skill_registry
from integrations.hermes_client import hermes_client

logger = logging.getLogger("hermes_browser_skill")

async def scrape_webpage_with_hermes(url: str, extraction_instructions: str = "") -> str:
    """
    Scrape and extract unstructured data from a URL using Hermes headless browser.
    
    Use this tool to read live SEC filings, earnings transcripts, or company
    press releases that are not available via structured financial APIs.
    
    Args:
        url: The URL to scrape (e.g., https://www.sec.gov/Archives/edgar/data/...)
        extraction_instructions: Specific instructions on what data to extract 
                               (e.g., "Extract Q3 Revenue and Forward Guidance").
                               
    Returns:
        A string containing the extracted content or an error message.
    """
    logger.info(f"Fundamental Analyst requested scrape of: {url}")
    
    result = await hermes_client.scrape_url(url=url, instructions=extraction_instructions)
    
    if result.get("success"):
        content = result.get("content", "")
        if len(content) > 15000:
            logger.warning(f"Extracted content from {url} is very long ({len(content)} chars), truncating.")
            return content[:15000] + "\n...[TRUNCATED FOR LENGTH]"
        return content
    else:
        error = result.get("error", "Unknown error")
        logger.error(f"Scrape failed for {url}: {error}")
        return f"Failed to scrape {url}. Error: {error}"


# Register the skill for the Fundamental Analyst
_skill_registry.register_skill(
    "fundamental_analyst",
    "scrape_webpage_with_hermes",
    scrape_webpage_with_hermes,
    description="Scrape and extract unstructured data from a URL using Hermes headless browser. Ideal for SEC filings or investor relations pages."
)
