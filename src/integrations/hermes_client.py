"""
Hermes Agent Client

Provides an asynchronous HTTP client to interface with the external Hermes Agent.
Used primarily for executing untrusted code in isolated Modal/Docker sandboxes,
delegating web scraping tasks, and orchestrating sub-agents.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp
from config.settings import get_settings

logger = logging.getLogger("hermes_client")


class HermesClient:
    """Async client for communicating with the Hermes Agent API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.hermes_api_url.rstrip("/")
        self.api_key = self.settings.hermes_api_key
        self.default_backend = self.settings.hermes_sandbox_backend

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def execute_in_sandbox(
        self, code: str, backend: Optional[str] = None, timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute arbitrary Python code in an isolated Hermes sandbox.
        
        Args:
            code: The Python script string to execute.
            backend: The sandbox backend to use (local, docker, modal, singularity).
            timeout: Maximum execution time in seconds.
            
        Returns:
            Dict containing 'success', 'stdout', 'stderr', and 'exit_code'.
        """
        target_backend = backend or self.default_backend
        url = f"{self.base_url}/v1/execute"
        
        payload = {
            "code": code,
            "backend": target_backend,
            "timeout_seconds": timeout,
        }

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.post(url, json=payload, timeout=timeout + 5) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Hermes execution failed [{response.status}]: {error_text}")
                        return {
                            "success": False,
                            "stdout": "",
                            "stderr": f"HTTP Error {response.status}: {error_text}",
                            "exit_code": 1
                        }
                    
                    data = await response.json()
                    
                    return {
                        "success": data.get("exit_code", 1) == 0,
                        "stdout": data.get("stdout", ""),
                        "stderr": data.get("stderr", ""),
                        "exit_code": data.get("exit_code", 1)
                    }

        except asyncio.TimeoutError:
            logger.error("Hermes execution timed out.")
            return {
                "success": False,
                "stdout": "",
                "stderr": "Execution timed out.",
                "exit_code": 124
            }
        except aiohttp.ClientError as e:
            logger.error(f"Hermes Client connection error: {str(e)}")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Connection error: {str(e)}",
                "exit_code": 1
            }
        except Exception as e:
            logger.exception("Unexpected error in Hermes execute_in_sandbox")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Internal client error: {str(e)}",
                "exit_code": 1
            }

    async def scrape_url(
        self, url: str, instructions: Optional[str] = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Use Hermes Headless Playwright to scrape unstructured data from a URL.
        
        Args:
            url: The target website URL.
            instructions: Optional LLM instructions for semantic extraction.
            timeout: Maximum execution time in seconds.
            
        Returns:
            Dict containing 'success', 'content', and 'error'.
        """
        api_url = f"{self.base_url}/v1/browser/scrape"
        payload = {
            "url": url,
            "instructions": instructions or "Extract the main textual content.",
            "timeout_seconds": timeout,
        }

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.post(api_url, json=payload, timeout=timeout + 5) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Hermes browser scrape failed [{response.status}]: {error_text}")
                        return {
                            "success": False,
                            "content": "",
                            "error": f"HTTP Error {response.status}: {error_text}"
                        }
                    
                    data = await response.json()
                    return {
                        "success": True,
                        "content": data.get("content", ""),
                        "error": ""
                    }
        except asyncio.TimeoutError:
            logger.error(f"Hermes scrape timed out for {url}.")
            return {"success": False, "content": "", "error": "Scrape timed out."}
        except Exception as e:
            logger.exception(f"Unexpected error in Hermes scrape_url for {url}")
            return {"success": False, "content": "", "error": str(e)}

    async def analyze_image(
        self, image_url: str, instructions: Optional[str] = None, timeout: int = 60
    ) -> Dict[str, Any]:
        """
        Use Hermes Vision API to analyze and extract data from an image/chart.
        
        Args:
            image_url: The URL of the image to analyze.
            instructions: Prompt instructing the vision model what to look for.
            timeout: Maximum execution time in seconds.
            
        Returns:
            Dict containing 'success', 'analysis', and 'error'.
        """
        api_url = f"{self.base_url}/v1/vision/analyze"
        payload = {
            "image_url": image_url,
            "instructions": instructions or "Describe this image in detail.",
            "timeout_seconds": timeout,
        }

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.post(api_url, json=payload, timeout=timeout + 5) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Hermes vision analysis failed [{response.status}]: {error_text}")
                        return {
                            "success": False,
                            "analysis": "",
                            "error": f"HTTP Error {response.status}: {error_text}"
                        }
                    
                    data = await response.json()
                    return {
                        "success": True,
                        "analysis": data.get("analysis", ""),
                        "error": ""
                    }
        except asyncio.TimeoutError:
            logger.error(f"Hermes vision analysis timed out for {image_url}.")
            return {"success": False, "analysis": "", "error": "Analysis timed out."}
        except Exception as e:
            logger.exception(f"Unexpected error in Hermes analyze_image for {image_url}")
            return {"success": False, "analysis": "", "error": str(e)}

    async def dispatch_subagent(
        self, task_prompt: str, context: Optional[Dict[str, Any]] = None, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Dispatch a background sub-agent via Hermes to perform intensive async work.
        
        Args:
            task_prompt: The instructions for the sub-agent.
            context: Optional dictionary of context (e.g. historical trade data).
            timeout: Maximum execution time in seconds (default 5 mins for backtests).
            
        Returns:
            Dict containing 'success', 'result', and 'error'.
        """
        api_url = f"{self.base_url}/v1/agents/dispatch"
        payload = {
            "prompt": task_prompt,
            "context": context or {},
            "timeout_seconds": timeout,
        }

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.post(api_url, json=payload, timeout=timeout + 5) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Hermes subagent dispatch failed [{response.status}]: {error_text}")
                        return {
                            "success": False,
                            "result": {},
                            "error": f"HTTP Error {response.status}: {error_text}"
                        }
                    
                    data = await response.json()
                    return {
                        "success": True,
                        "result": data.get("result", {}),
                        "error": ""
                    }
        except asyncio.TimeoutError:
            logger.error("Hermes subagent dispatch timed out.")
            return {"success": False, "result": {}, "error": "Dispatch timed out."}
        except Exception as e:
            logger.exception("Unexpected error in Hermes dispatch_subagent")
            return {"success": False, "result": {}, "error": str(e)}

    async def health_check(self) -> bool:
        """Check if the Hermes API is reachable."""
        url = f"{self.base_url}/health"
        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                async with session.get(url, timeout=5) as response:
                    return response.status == 200
        except Exception:
            return False

# Singleton instance
hermes_client = HermesClient()
