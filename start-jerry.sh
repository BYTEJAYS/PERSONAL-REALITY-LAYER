#!/usr/bin/env bash
# start-jerry.sh — bring Jerry's LLM voice online. Run this after a restart
# whenever you want Jerry to use the smart (8b) voice.
#
# Light footprint: the model UNLOADS from RAM ~5 min after your last message,
# so when you're not actively chatting it costs almost nothing. To shut the
# whole thing down and reclaim everything, run ./stop-jerry.sh
set -euo pipefail

MODEL="llama3.1:8b"
LOG_DIR="$HOME/.jerry"
URL_FILE="$LOG_DIR/url"
mkdir -p "$LOG_DIR"

# --- locate a binary across known spots; self-heal the ~/.local/bin symlink ---
# Usage: find_bin <name> <symlink-path> <candidate1> [candidate2 ...]
find_bin() {
  local name="$1" link="$2"; shift 2
  local found=""
  # prefer the symlink if it actually resolves to an executable
  if [ -x "$link" ]; then found="$link"; fi
  if [ -z "$found" ]; then
    local c
    for c in "$@"; do [ -x "$c" ] && { found="$c"; break; }; done
  fi
  # last resort: anything already on PATH
  if [ -z "$found" ]; then found="$(command -v "$name" 2>/dev/null || true)"; fi
  if [ -z "$found" ]; then
    echo "✗ $name not found — install it or check its location" >&2
    return 1
  fi
  # repoint the convenience symlink if it's missing/stale
  if [ "$found" != "$link" ]; then
    mkdir -p "$(dirname "$link")"
    ln -sf "$found" "$link"
    echo "↻ fixed $link → $found"
  fi
  printf '%s\n' "$found"
}

OLLAMA="$(find_bin ollama "$HOME/.local/bin/ollama" \
  "/Applications/Ollama.app/Contents/Resources/ollama" \
  "$HOME/Applications/Ollama.app/Contents/Resources/ollama")" || exit 1

CLOUDFLARED="$(find_bin cloudflared "$HOME/.local/bin/cloudflared" \
  "/opt/homebrew/bin/cloudflared" \
  "/usr/local/bin/cloudflared")" || exit 1

# Model leaves RAM 5 min after the last message (frees ~5GB, saves battery).
# It reloads in ~5-10s on the next message, then stays warm while you chat.
export OLLAMA_KEEP_ALIVE=5m

# 1) Ollama server -----------------------------------------------------------
if curl -s http://localhost:11434/api/tags -m 3 >/dev/null 2>&1; then
  echo "✓ Ollama already running"
else
  echo "▸ starting Ollama..."
  nohup "$OLLAMA" serve >"$LOG_DIR/ollama.log" 2>&1 &
  up=""
  for _ in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags -m 3 >/dev/null 2>&1; then up=1; break; fi
    sleep 1
  done
  if [ -z "$up" ]; then
    echo "✗ Ollama didn't come up within 30s. Last log lines:"
    tail -n 15 "$LOG_DIR/ollama.log" 2>/dev/null | sed 's/^/    /'
    echo "  (a stuck process on :11434? try ./stop-jerry.sh then retry)"
    exit 1
  fi
  echo "✓ Ollama up (loads the model on the first message, then keeps it warm)"
fi

# Make sure the model exists (no-op if already downloaded).
if ! "$OLLAMA" list | grep -q "$MODEL"; then
  echo "▸ pulling $MODEL (first time only)..."
  "$OLLAMA" pull "$MODEL"
fi

# 2) cloudflared tunnel (one fresh tunnel -> one known URL) -------------------
pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1
: >"$LOG_DIR/cloudflared.log"   # truncate so we read THIS run's URL, not a stale one
echo "▸ starting tunnel..."
nohup "$CLOUDFLARED" tunnel --url http://localhost:11434 \
  --http-host-header localhost:11434 >"$LOG_DIR/cloudflared.log" 2>&1 &

URL=""
for _ in $(seq 1 40); do
  URL=$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" | head -1 || true)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "✗ tunnel URL not found within 40s. Last log lines:"
  tail -n 15 "$LOG_DIR/cloudflared.log" 2>/dev/null | sed 's/^/    /'
  exit 1
fi

# Remember the URL + copy it to the clipboard for the Railway paste.
printf '%s\n' "$URL" >"$URL_FILE"
printf '%s' "$URL" | pbcopy 2>/dev/null && CLIP=" (copied to clipboard)" || CLIP=""

# Best-effort sanity check that the tunnel actually reaches Ollama.
if curl -s -m 8 "$URL/api/version" >/dev/null 2>&1; then
  HEALTH="✓ tunnel reaches Ollama"
else
  HEALTH="· tunnel up (couldn't self-verify from here — usually still fine)"
fi

cat <<EOF

════════════════════════════════════════════════════════════════
  Jerry is ONLINE.   $HEALTH

  Tunnel URL$CLIP:
      $URL

  → If this URL changed since last time, update it on Railway:
      API service → Variables → OLLAMA_URL = $URL  → redeploy.
    (Same URL as before? Then do nothing.)
    Saved to: $URL_FILE

  • Light on RAM/battery — model unloads ~5 min after you stop chatting.
  • Shut it all down anytime:   ./stop-jerry.sh
  • You can close this window; Jerry keeps running in the background.
════════════════════════════════════════════════════════════════
EOF
