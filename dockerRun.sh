#!/bin/bash

# Get the absolute path of the script's location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_WORKSPACE="$SCRIPT_DIR"
REMOTE_WORKSPACE='/workspace'

echo "Using LOCAL_WORKSPACE: $LOCAL_WORKSPACE"
echo "Using REMOTE_WORKSPACE: $REMOTE_WORKSPACE"

# Run Docker, disabling path conversion on Windows
MSYS_NO_PATHCONV=1 docker run --rm -it \
    --ipc=host --ulimit memlock=-1 --ulimit stack=67108864 \
    --name nvflare-dev \
    -v "$LOCAL_WORKSPACE:$REMOTE_WORKSPACE" \
    -w "$REMOTE_WORKSPACE" \
    nvflare-dev:latest