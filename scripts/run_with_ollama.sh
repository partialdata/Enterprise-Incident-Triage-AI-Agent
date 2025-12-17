#!/usr/bin/env bash
set -euo pipefail

# Helper to choose docker compose command
if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "docker compose/docker-compose not found" >&2
  exit 1
fi

MODEL="${OLLAMA_MODEL:-llama3}"
PORT="${OLLAMA_PORT:-11434}"

ensure_port() {
  local port="$1"
  if lsof -i :"$port" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

pick_port() {
  local port="$1"
  if ensure_port "$port"; then
    echo "$port"
    return 0
  fi
  # If user specified a port, do not override—fail fast
  if [ -n "${OLLAMA_PORT:-}" ]; then
    echo "Port $port is in use; set OLLAMA_PORT to a free port or stop the service on that port." >&2
    exit 1
  fi
  # Auto-fallback when default 11434 is busy
  for candidate in 11435 11436 11437; do
    if ensure_port "$candidate"; then
      echo "Port 11434 busy; using fallback port $candidate for Ollama" >&2
      echo "$candidate"
      return 0
    fi
  done
  echo "No free fallback port found (tried 11434,11435,11436,11437)." >&2
  exit 1
}

PORT="$(pick_port "$PORT")"
export OLLAMA_PORT="$PORT"

usage() {
  cat <<'EOF'
Usage: scripts/run_with_ollama.sh [up|down]

up   - build images, start Ollama, pull model, start app
down - stop containers (preserves Ollama volume)
EOF
}

cmd="${1:-up}"

case "$cmd" in
  up)
    # Clean up any stale containers from previous runs to avoid name conflicts
    docker rm -f incident-triage >/dev/null 2>&1 || true
    docker rm -f ollama >/dev/null 2>&1 || true

    $COMPOSE_CMD build
    $COMPOSE_CMD up -d ollama
    # Entry point is already `ollama serve`, so exec into the running container to pull model.
    $COMPOSE_CMD exec ollama ollama pull "$MODEL"
    $COMPOSE_CMD up -d app
    echo "App: http://127.0.0.1:8000 (LLM via Ollama @ http://localhost:$PORT, model=$MODEL)"
    ;;
  down)
    $COMPOSE_CMD down
    ;;
  *)
    usage
    exit 1
    ;;
esac
