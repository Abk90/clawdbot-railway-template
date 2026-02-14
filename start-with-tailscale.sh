#!/bin/bash
set -e

# If TS_AUTHKEY is set, start Tailscale
if [ -n "$TS_AUTHKEY" ]; then
  echo "[tailscale] Starting tailscaled..."

  # Persist Tailscale state across redeploys using the Railway volume
  TS_STATE_DIR="/data/tailscale"
  mkdir -p "$TS_STATE_DIR"

  # Use default socket path so OpenClaw's built-in integration can find it
  mkdir -p /var/run/tailscale

  # Start tailscaled with userspace networking (no /dev/net/tun in containers)
  tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --tun=userspace-networking &

  # Wait for tailscaled to be ready
  for i in $(seq 1 15); do
    if tailscale status >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  # Bring up Tailscale (--reset to avoid conflicts with persisted state)
  echo "[tailscale] Connecting to Tailscale network..."
  tailscale up \
    --authkey="$TS_AUTHKEY" \
    --hostname="${TS_HOSTNAME:-openclaw-railway}" \
    --reset

  TS_IP=$(tailscale ip -4 2>/dev/null || echo "pending")
  echo "[tailscale] Connected! IP: $TS_IP"
else
  echo "[tailscale] TS_AUTHKEY not set, skipping Tailscale"
fi

# Start the main application
exec node src/server.js
