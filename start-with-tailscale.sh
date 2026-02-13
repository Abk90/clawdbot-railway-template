#!/bin/bash
set -e

# If TS_AUTHKEY is set, start Tailscale
if [ -n "$TS_AUTHKEY" ]; then
  echo "[tailscale] Starting tailscaled..."

  # Use /data/tailscale for persistent state (survives redeploys)
  TS_STATE_DIR="${TS_STATE_DIR:-/data/tailscale}"
  mkdir -p "$TS_STATE_DIR"

  # Start tailscaled with userspace networking (no /dev/net/tun in containers)
  tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --tun=userspace-networking \
    --socket="$TS_STATE_DIR/tailscaled.sock" &

  # Wait for tailscaled to be ready
  for i in $(seq 1 10); do
    if tailscale --socket="$TS_STATE_DIR/tailscaled.sock" status >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  # Bring up Tailscale
  echo "[tailscale] Connecting to Tailscale network..."
  tailscale --socket="$TS_STATE_DIR/tailscaled.sock" up \
    --authkey="$TS_AUTHKEY" \
    --hostname="${TS_HOSTNAME:-openclaw-railway}"

  TS_IP=$(tailscale --socket="$TS_STATE_DIR/tailscaled.sock" ip -4 2>/dev/null || echo "pending")
  echo "[tailscale] Connected! IP: $TS_IP"
else
  echo "[tailscale] TS_AUTHKEY not set, skipping Tailscale"
fi

# Start the main application
exec node src/server.js
