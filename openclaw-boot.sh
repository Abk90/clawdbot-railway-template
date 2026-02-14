#!/bin/bash
set -e

# ============================================================
# OpenClaw Boot Script
# Tailscale + Auto-update OpenClaw + Start wrapper server
# ============================================================

# --- 1. Tailscale ---
if [ -n "$TS_AUTHKEY" ]; then
  echo "[tailscale] Starting tailscaled..."

  TS_STATE_DIR="/data/tailscale"
  mkdir -p "$TS_STATE_DIR"
  mkdir -p /var/run/tailscale

  tailscaled \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --tun=userspace-networking &

  for i in $(seq 1 15); do
    if tailscale status >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

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

# --- 2. Auto-update OpenClaw ---
echo "[boot] Checking for OpenClaw updates..."
CURRENT_VERSION=$(openclaw --version 2>/dev/null || echo "unknown")
echo "[boot] Current version: $CURRENT_VERSION"

if openclaw update 2>&1; then
  NEW_VERSION=$(openclaw --version 2>/dev/null || echo "unknown")
  if [ "$CURRENT_VERSION" != "$NEW_VERSION" ]; then
    echo "[boot] Updated from $CURRENT_VERSION to $NEW_VERSION"
  else
    echo "[boot] Already on latest ($CURRENT_VERSION)"
  fi
else
  echo "[boot] Update check failed, continuing with $CURRENT_VERSION"
fi

# --- 3. Start the wrapper server ---
echo "[boot] Starting OpenClaw wrapper server..."
exec node /app/src/server.js
