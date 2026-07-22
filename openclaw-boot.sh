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
      if (!cfg.channels) cfg.channels = {};

      if (process.env.TELEGRAM_BOT_TOKEN) {
        if (!cfg.channels.telegram) {
          // Token is set but telegram section was removed — restore it
          console.log('[boot]   TELEGRAM_BOT_TOKEN set — restoring telegram channel config');
          cfg.channels.telegram = {
            botToken: '\$TELEGRAM_BOT_TOKEN',
            dmPolicy: 'open'
          };
          changed = true;
        } else {
          const tg = cfg.channels.telegram;
          // Fix invalid dmPolicy
          const validPolicies = ['pairing', 'allowlist', 'open', 'disabled'];
          if (tg.dmPolicy && !validPolicies.includes(tg.dmPolicy)) {
            console.log('[boot]   Fixing telegram.dmPolicy:', tg.dmPolicy, '-> open');
            tg.dmPolicy = 'open';
            changed = true;
          }
          // Remove unrecognized key
          if ('debounceMs' in tg) {
            console.log('[boot]   Removing unrecognized key: telegram.debounceMs');
            delete tg.debounceMs;
            changed = true;
          }
        }
      } else {
        // No token — remove telegram to prevent fatal error
        if (cfg.channels.telegram) {
          console.log('[boot]   TELEGRAM_BOT_TOKEN not set — removing telegram channel config');
          delete cfg.channels.telegram;
          changed = true;
        }
      }

      // Migrate provider api values renamed in OpenClaw v2026.6.x
      // (old codex api ids are rejected by the new config schema and
      // block gateway startup entirely)
      const allowedApis = ['openai-completions','openai-responses','openai-chatgpt-responses','anthropic-messages','google-generative-ai','google-vertex','github-copilot','bedrock-converse-stream','ollama','azure-openai-responses'];
      const providers = cfg.models && cfg.models.providers;
      if (providers && typeof providers === 'object') {
        for (const pid of Object.keys(providers)) {
          const p = providers[pid];
          if (!p || typeof p !== 'object') continue;
          const isCodex = pid.includes('codex') || String(p.api || '').includes('codex');
          if (p.api && !allowedApis.includes(p.api) && isCodex) {
            console.log('[boot]   Migrating models.providers.' + pid + '.api:', p.api, '-> openai-chatgpt-responses');
            p.api = 'openai-chatgpt-responses';
            changed = true;
          }
          if (Array.isArray(p.models)) {
            for (const m of p.models) {
              if (m && m.api && !allowedApis.includes(m.api) && (isCodex || String(m.api).includes('codex'))) {
                console.log('[boot]   Migrating model api in provider ' + pid + ':', m.api, '-> openai-chatgpt-responses');
                m.api = 'openai-chatgpt-responses';
                changed = true;
              }
            }
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

# --- 2d. Post-upgrade doctor repair (migrates legacy codex refs + auth profiles) ---
# v2026.6.x renamed the codex provider route to openai/* ; doctor --fix migrates
# legacy model refs, auth profile ids and auth order to the canonical route.
# Idempotent — safe to run on every boot. Never blocks startup on failure.
echo "[boot] Running openclaw doctor --fix (non-interactive, post-upgrade repairs)..."
OPENCLAW_STATE_DIR="$OC_STATE" \
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${CLAWDBOT_WORKSPACE_DIR:-/data/workspace}}" \
  timeout 120 openclaw doctor --fix --non-interactive 2>&1 | tail -40 || echo "[boot]   doctor exited non-zero (non-blocking, continuing boot)"

# --- 3. Start the wrapper server (supervised, nightly preventive restart) ---
# 4 incidents in 7 weeks (06/06, 07/07, 15/07, 21/07): the container degrades
# after ~6-7 days of uptime (progressive process/thread leak) until the codex
# app-server can no longer spawn ("startup aborted", then EAGAIN/Cannot fork).
# A fresh container every night keeps it far from the degradation zone.
# State lives on the /data volume, so nothing is lost across restarts.
echo "[boot] Starting OpenClaw wrapper server..."
node /app/src/server.js &
WRAPPER_PID=$!

trap 'echo "[boot] SIGTERM received - stopping wrapper"; kill -TERM "$WRAPPER_PID" 2>/dev/null' TERM

RESTART_AT="${OPENCLAW_NIGHTLY_RESTART_UTC:-03:30}"
(
  now=$(date +%s)
  target=$(date -d "$RESTART_AT" +%s 2>/dev/null || echo 0)
  if [ "$target" -gt 0 ]; then
    [ "$target" -le "$now" ] && target=$((target + 86400))
    # Guarantee at least 2h uptime (avoid restart loop right after a deploy)
    [ $((target - now)) -lt 7200 ] && target=$((target + 86400))
    echo "[boot] Preventive nightly restart scheduled for $(date -u -d "@$target" '+%Y-%m-%d %H:%M UTC')"
    sleep $((target - now))
    echo "[boot] Preventive nightly restart: stopping wrapper so Railway starts a fresh container..."
    kill -TERM "$WRAPPER_PID" 2>/dev/null
    sleep 15
    kill -KILL "$WRAPPER_PID" 2>/dev/null
  fi
) &

wait "$WRAPPER_PID"
code=$?
echo "[boot] wrapper exited (code=$code) - exiting 1 so Railway restarts the container"
exit 1
