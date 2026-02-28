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

# --- 2. OpenClaw version ---
CURRENT_VERSION=$(openclaw --version 2>/dev/null || echo "unknown")
echo "[boot] OpenClaw version: $CURRENT_VERSION"
# Runtime auto-update is disabled — it breaks pnpm dep resolution (missing
# packages like strip-ansi, @aws-sdk/client-bedrock after git pull overwrites
# .npmrc hoisting config). Version upgrades are managed via Dockerfile
# OPENCLAW_GIT_REF and redeployed through Railway.

# --- 2b. Session cleanup (prevents OOM from bloated sessions) ---
OC_STATE="${OPENCLAW_STATE_DIR:-${CLAWDBOT_STATE_DIR:-/data/.clawdbot}}"
if [ "${OPENCLAW_PURGE_SESSIONS:-}" = "1" ]; then
  echo "[boot] OPENCLAW_PURGE_SESSIONS=1 — purging session data to prevent OOM..."
  echo "[boot] State dir contents before purge:"
  ls -la "$OC_STATE/" 2>/dev/null || true
  du -sh "$OC_STATE"/* 2>/dev/null || true

  # Keep ONLY: config files (*.json at root), gateway.token, canvas/, credentials/
  # Remove everything else that could hold session data.
  for item in "$OC_STATE"/*; do
    base=$(basename "$item")
    case "$base" in
      *.json|gateway.token|canvas|credentials|whatsapp-auth|telegram-auth)
        echo "[boot]   keeping $base"
        ;;
      *)
        echo "[boot]   removing $base"
        rm -rf "$item"
        ;;
    esac
  done
  # Also handle hidden dirs (but not . or ..)
  for item in "$OC_STATE"/.*; do
    base=$(basename "$item")
    case "$base" in
      .|..) continue ;;
      *)
        echo "[boot]   removing hidden: $base"
        rm -rf "$item"
        ;;
    esac
  done
  echo "[boot] Session purge complete."
  echo "[boot] State dir contents after purge:"
  ls -la "$OC_STATE/" 2>/dev/null || true
fi

# --- 3. Start the wrapper server ---
echo "[boot] Starting OpenClaw wrapper server..."
exec node /app/src/server.js
