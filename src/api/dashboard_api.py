from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
import logging
import sys
import os

# Add src directory to path to import skills
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.skills.database.fetch_top_stocks import fetch_top_20_stocks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)

@router.get("/top-stocks", response_model=List[Dict[str, Any]])
async def get_top_20_stocks():
    """
    API endpoint to fetch the current top 20 selected stocks from the database.
    This endpoint is consumed by the frontend dashboard to display the list 
    of top 20 stocks selected to be traded.
    """
    try:
        logger.info("Received request to fetch top 20 stocks for dashboard.")
        stocks = fetch_top_20_stocks()
        
        if not stocks:
            logger.info("No top stocks found in the database. Returning empty list.")
            # Return empty list instead of 404 so the dashboard can render an empty state gracefully
            return []
            
        return stocks
    except Exception as e:
        logger.error(f"Error in get_top_20_stocks endpoint: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch top stocks from database: {str(e)}"
        )
