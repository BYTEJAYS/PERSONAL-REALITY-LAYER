#!/usr/bin/env bash
# stop-jerry.sh — take Jerry's local engine fully offline (frees RAM + battery).
# After this, Jerry falls back to its simple built-in voice until you run
# ./start-jerry.sh again.
LOG_DIR="$HOME/.jerry"
echo "Stopping Jerry's tunnel and model server…"

# Try a graceful kill, then a forced one, and confirm the process is actually gone.
kill_match() {
  local label="$1" pat="$2"
  if ! pgrep -f "$pat" >/dev/null 2>&1; then
    echo "· $label wasn't running"
    return 0
  fi
  pkill -f "$pat" 2>/dev/null || true
  for _ in $(seq 1 10); do
    pgrep -f "$pat" >/dev/null 2>&1 || { echo "✓ $label stopped"; return 0; }
    sleep 0.5
  done
  # still alive → force it
  pkill -9 -f "$pat" 2>/dev/null || true
  sleep 1
  if pgrep -f "$pat" >/dev/null 2>&1; then
    echo "✗ $label wouldn't stop — check manually (pgrep -f '$pat')"
  else
    echo "✓ $label stopped (forced)"
  fi
}

kill_match "tunnel" "cloudflared tunnel"
kill_match "ollama" "ollama serve"

# Forget the saved tunnel URL (it's dead now and would mislead next time).
rm -f "$LOG_DIR/url" 2>/dev/null || true

echo "Done. Run ./start-jerry.sh when you want the smart voice back."
