#!/usr/bin/env bash
# Boot Ollama, then make sure the model is present before we're "done".
#
# OLLAMA_HOST is set to [::]:11434 (IPv6 any, for Railway private networking).
# That same value would make the *client* commands below try to dial [::], which
# is the wrong target, so we point the client at 127.0.0.1 — the [::] listener is
# dual-stack on Linux, so the loopback connection lands on the same server.
set -euo pipefail

MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
CLIENT_HOST="127.0.0.1:11434"

# Start the server (binds OLLAMA_HOST = [::]:11434) in the background.
ollama serve &
server_pid=$!

# Wait for the API to accept connections.
echo "[entrypoint] waiting for ollama server..."
until OLLAMA_HOST="${CLIENT_HOST}" ollama list >/dev/null 2>&1; do
  # If the server died while we were waiting, fail loudly.
  kill -0 "${server_pid}" 2>/dev/null || { echo "[entrypoint] ollama server exited early"; wait "${server_pid}"; exit 1; }
  sleep 1
done

# Pull the model if it isn't already on the persisted volume (idempotent).
echo "[entrypoint] ensuring model '${MODEL}' is present (first boot downloads it)..."
OLLAMA_HOST="${CLIENT_HOST}" ollama pull "${MODEL}"
echo "[entrypoint] ready — serving '${MODEL}' on ${OLLAMA_HOST}"

# Hand the foreground back to the server so the container stays alive / logs flow.
wait "${server_pid}"
