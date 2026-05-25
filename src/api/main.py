from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.dashboard_api import router as dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SelfEvolve Trading System API",
    description="Backend API for the SelfEvolve autonomous trading system dashboard",
    version="1.0.0"
)

# Configure CORS for dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include routers
app.include_router(dashboard_router)

@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "online", "service": "SelfEvolve API"}

if __name__ == "__main__":
    logger.info("Starting SelfEvolve API server...")
    # Run the API server on port 8000
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
