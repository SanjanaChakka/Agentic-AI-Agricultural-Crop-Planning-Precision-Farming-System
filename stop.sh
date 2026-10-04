#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Stops the app. The database lives in a Docker volume, so demo data and any
#  approvals you recorded survive a stop/start.
#
#    ./stop.sh          stop, keep data
#    ./stop.sh --purge  stop and delete the database volume too
# ---------------------------------------------------------------------------
set -uo pipefail

cd "$(dirname "$0")"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
else
  COMPOSE=(docker-compose)
fi

PURGE=""
if [ "${1:-}" = "--purge" ]; then
  PURGE="-v"
  printf 'This deletes the database volume: demo data and recorded approvals are lost.\n'
  read -r -p 'Type yes to confirm: ' reply
  [ "$reply" = "yes" ] || { printf 'Cancelled.\n'; exit 0; }
fi

if ! "${COMPOSE[@]}" down $PURGE; then
  printf '\nCould not reach Docker. Is Docker Desktop running?\n'
  exit 1
fi

printf '\nStopped.\n'
if [ -z "$PURGE" ]; then
  printf 'Your data is kept in the Docker volume "appdata". Run ./start.sh to start again.\n'
fi
