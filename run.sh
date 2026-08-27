#!/usr/bin/env bash
# Build (if needed) and run Archagent in Docker.
#
# Usage:
#   ./run.sh                    # build + run, http://127.0.0.1:8000
#   ARCHAGENT_PORT=9000 ./run.sh
#   ANTHROPIC_API_KEY=sk-ant-... ./run.sh
#
# Project data (uploaded files, versions, run output) persists in a Docker
# volume across restarts. To connect to a live Revit/AutoCAD add-in running
# on THIS SAME machine, use revit://host.docker.internal:PORT in the web UI's
# CAD field, not 127.0.0.1 - see DOCKER.md for why.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

IMAGE="archagent:latest"
CONTAINER="archagent"
PORT="${ARCHAGENT_PORT:-8000}"

if ! docker info >/dev/null 2>&1; then
  echo "Docker does not seem to be running - start Docker Desktop (or the Docker daemon) and try again." >&2
  exit 1
fi

echo "==> Building the Archagent image (this only takes a while the first time)..."
docker build -t "$IMAGE" .

if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "==> Removing the previous container..."
  docker rm -f "$CONTAINER" >/dev/null
fi

echo "==> Starting Archagent on http://127.0.0.1:${PORT}"
echo "    (Ctrl+C stops it; project data is kept in the 'archagent-data' Docker volume)"
exec docker run --rm -it \
  --name "$CONTAINER" \
  -p "${PORT}:8000" \
  -v archagent-data:/data/projects \
  -e "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}" \
  --add-host=host.docker.internal:host-gateway \
  "$IMAGE"
