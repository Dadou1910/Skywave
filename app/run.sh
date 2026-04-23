#!/usr/bin/env bash
set -e

# Allow the Docker container to connect to the local X11 display
xhost +local:docker 2>/dev/null || true

docker compose up --build
