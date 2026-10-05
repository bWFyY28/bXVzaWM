#!/bin/sh
set -eu
compose_file=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/compose.yaml
if [ "$#" -eq 1 ] && [ "$1" = "--stop-service" ]; then
    exec docker compose -f "$compose_file" down
fi
docker compose -f "$compose_file" up -d --build --wait app
if [ "$#" -eq 0 ] || [ "$1" = "open" ]; then
    exec docker compose -f "$compose_file" exec app bxvzm --config data/container-config.json "$@"
fi
exec docker compose -f "$compose_file" exec -T app bxvzm --config data/container-config.json "$@"
