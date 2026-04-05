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

# --- 2c. Auto-repair config (fix known invalid keys) ---
OC_CONFIG="$OC_STATE/openclaw.json"
if [ -f "$OC_CONFIG" ]; then
  echo "[boot] Checking config for known issues..."
  TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" node -e "
    const fs = require('fs');
    const cfgPath = process.argv[1];
    let changed = false;
    try {
      const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      if (cfg.channels && cfg.channels.telegram) {
        const tg = cfg.channels.telegram;

        // If TELEGRAM_BOT_TOKEN is not set, remove the entire telegram channel
        // to prevent fatal MissingEnvVarError on botToken reference.
        if (!process.env.TELEGRAM_BOT_TOKEN) {
          console.log('[boot]   TELEGRAM_BOT_TOKEN not set — removing telegram channel config');
          delete cfg.channels.telegram;
          changed = true;
        } else {
          // Fix invalid dmPolicy
          const validPolicies = ['pairing', 'allowlist', 'open', 'disabled'];
          if (tg.dmPolicy && !validPolicies.includes(tg.dmPolicy)) {
            console.log('[boot]   Fixing telegram.dmPolicy:', tg.dmPolicy, '-> disabled');
            tg.dmPolicy = 'disabled';
            changed = true;
          }
          // Remove unrecognized key
          if ('debounceMs' in tg) {
            console.log('[boot]   Removing unrecognized key: telegram.debounceMs');
            delete tg.debounceMs;
            changed = true;
          }
        }
      }
      if (changed) {
        fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2) + '\n');
        console.log('[boot]   Config repaired successfully.');
      } else {
        console.log('[boot]   Config OK, no repairs needed.');
      }
    } catch (e) {
      console.error('[boot]   Config repair failed:', e.message);
    }
  " "$OC_CONFIG"
fi

# --- 3. Start the wrapper server ---
echo "[boot] Starting OpenClaw wrapper server..."
exec node /app/src/server.js
