#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "SkyWave — Brain Interface"
echo

if ! command -v docker &>/dev/null; then
    echo "Docker is required to run SkyWave on Linux."
    echo
    echo "Install it with:"
    echo "  sudo apt-get install docker.io docker-compose-plugin"
    echo "Or visit: https://docs.docker.com/engine/install/"
    exit 1
fi

# Allow the container to connect to the local X11 display
xhost +local:docker 2>/dev/null || true

echo "Building and launching (first run downloads dependencies, may take a minute)..."
echo
docker compose up --build
