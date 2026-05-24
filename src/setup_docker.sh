#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
# SelfEvolve — Docker Setup Script
#
# Installs Docker (if needed) and starts the full stack.
# Run with: sudo bash setup_docker.sh
# ═══════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════════════"
echo "  SelfEvolve Docker Setup"
echo "═══════════════════════════════════════════════════════════"

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with: sudo bash setup_docker.sh"
    exit 1
fi

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2
    systemctl enable docker
    systemctl start docker

    # Add current user to docker group
    ACTUAL_USER="${SUDO_USER:-$(whoami)}"
    usermod -aG docker "$ACTUAL_USER"
    echo "✅ Docker installed. User $ACTUAL_USER added to docker group."
    echo "   You may need to log out and back in for group changes."
else
    echo "✅ Docker already installed."
fi

# Verify .env exists
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and fill in your keys."
    exit 1
fi

echo ""
echo "🚀 Starting SelfEvolve stack..."
docker compose up -d --build

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  Stack Status"
echo "═══════════════════════════════════════════════════════════"
docker compose ps

echo ""
echo "📊 Dashboard:   http://localhost:8000"
echo "📉 Grafana:     http://localhost:3000 (admin / selfevolve)"
echo "📈 Prometheus:  http://localhost:9091"
echo ""
echo "Logs: docker compose logs -f selfevolve-core"
