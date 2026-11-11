#!/bin/bash
set -euo pipefail

REPO="$HOME/path/to/your/repo"   # <- change this
UV="/opt/homebrew/bin/uv"        # <- check with `which uv`

# On wake, Wi-Fi may not be back yet. Wait up to ~2 minutes.
for i in $(seq 1 24); do
  curl -sf -o /dev/null --max-time 5 https://boardgamegeek.com && break
  sleep 5
done

set -a
source "$HOME/.config/bgg-sync/env"
set +a

cd "$REPO"
exec "$UV" run main.py