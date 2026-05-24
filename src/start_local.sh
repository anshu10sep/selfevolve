#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# SelfEvolve — Local Development Startup Script
# 
# Runs the system without Docker using local processes.
# For Docker deployment, use: docker compose up -d
# ═══════════════════════════════════════════════════════════════════

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "  SelfEvolve — Local Development Mode"
echo "═══════════════════════════════════════════════════════════"

# Check for .env
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and fill in your keys."
    exit 1
fi

# Source the .env for local overrides
export $(grep -v '^#' .env | xargs)

# Override infrastructure URLs for local development
export POSTGRES_URL="postgresql+asyncpg://selfevolve:selfevolve@localhost:5432/selfevolve"
export REDIS_URL="redis://localhost:6379/0"
export QDRANT_URL="http://localhost:6333"

echo ""
echo "🔑 Gemini API Key: ${GEMINI_API_KEY:0:10}..."
echo "🏦 Alpaca Base URL: $ALPACA_BASE_URL"
echo "📊 Environment: $ENVIRONMENT"
echo ""

# Install Python dependencies if needed
echo "📦 Checking Python dependencies..."
pip install -q -r requirements.txt 2>/dev/null || {
    echo "Installing dependencies..."
    pip install -r requirements.txt
}

# Quick Gemini API test
echo "🧪 Testing Gemini API connection..."
python3 -c "
from langchain_google_genai import ChatGoogleGenerativeAI
import os
llm = ChatGoogleGenerativeAI(
    model='gemini-2.0-flash',
    google_api_key=os.environ['GEMINI_API_KEY'],
    temperature=0.0,
)
response = llm.invoke('Say OK')
print(f'   ✅ Gemini API working: {response.content[:50]}')
" 2>&1 || echo "   ⚠️ Gemini API test failed (may need dependencies)"

echo ""
echo "🚀 Starting SelfEvolve system..."
echo "   Dashboard: http://localhost:8000"
echo "   Press Ctrl+C to stop"
echo ""

python3 main.py
