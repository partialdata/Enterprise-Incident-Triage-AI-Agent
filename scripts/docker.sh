#!/usr/bin/env sh
set -e

IMAGE_NAME="incident-triage:local"
CONTAINER_NAME="incident-triage"

case "$1" in
  start)
    docker build -t "$IMAGE_NAME" .
    docker run -d --rm -p 8000:8000 --name "$CONTAINER_NAME" "$IMAGE_NAME"
    echo "Service started at http://127.0.0.1:8000"
    ;;
  stop)
    docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || echo "Container not running"
    ;;
  *)
    echo "Usage: scripts/docker.sh {start|stop}"
    exit 1
    ;;
esac
