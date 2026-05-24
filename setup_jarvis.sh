#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# Jarvis Setup Script — Always-On Local Deployment
# ══════════════════════════════════════════════════════════════════
# Run: chmod +x setup_jarvis.sh && sudo ./setup_jarvis.sh

set -e

echo "🤖 Setting up Jarvis for always-on operation..."

# Create log directory
mkdir -p /home/agentx/self-evolving/logs
chown agentx:agentx /home/agentx/self-evolving/logs

# Copy systemd service
cp /home/agentx/self-evolving/jarvis.service /etc/systemd/system/jarvis.service

# Reload systemd
systemctl daemon-reload

# Enable on boot
systemctl enable jarvis.service

echo ""
echo "✅ Jarvis service installed and enabled on boot."
echo ""
echo "Commands:"
echo "  sudo systemctl start jarvis     # Start Jarvis"
echo "  sudo systemctl stop jarvis      # Stop Jarvis"
echo "  sudo systemctl restart jarvis   # Restart Jarvis"
echo "  sudo systemctl status jarvis    # Check status"
echo "  journalctl -u jarvis -f         # Live logs"
echo "  tail -f ~/self-evolving/logs/jarvis.log  # App logs"
echo ""
echo "Dashboard will be available at: http://localhost:8000"
echo ""
