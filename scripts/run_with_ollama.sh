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
    $COMPOSE_CMD build
    $COMPOSE_CMD up -d ollama
    $COMPOSE_CMD run --rm ollama ollama pull "$MODEL"
    $COMPOSE_CMD up -d app
    echo "App: http://127.0.0.1:8000 (LLM via Ollama @ http://localhost:11434, model=$MODEL)"
    ;;
  down)
    $COMPOSE_CMD down
    ;;
  *)
    usage
    exit 1
    ;;
esac
