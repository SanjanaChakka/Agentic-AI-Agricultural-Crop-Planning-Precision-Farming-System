#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  One-click launcher for macOS and Linux.
#
#    chmod +x start.sh && ./start.sh
#
#  Checks Docker, picks a free port, starts the stack with demo data seeded,
#  waits for the backend to report healthy, then opens the browser.
#  No API keys and no database server are required.
# ---------------------------------------------------------------------------
set -uo pipefail

cd "$(dirname "$0")"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
good() { printf '    \033[32m%s\033[0m\n' "$1"; }
bad()  { printf '    \033[31m%s\033[0m\n' "$1"; }
die()  { bad "$1"; printf '\n'; read -r -p 'Press Enter to close' _; exit 1; }

# --- 1. Docker --------------------------------------------------------------
step 'Checking Docker'
command -v docker >/dev/null 2>&1 \
  || die 'Docker was not found. Install Docker Desktop: https://www.docker.com/products/docker-desktop'

if ! docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  die 'Docker is installed but the engine is not responding. Start Docker Desktop and run this again.'
fi
good "Docker engine $(docker version --format '{{.Server.Version}}') is running"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die 'Neither "docker compose" nor "docker-compose" is available.'
fi

# --- 2. Free ports ----------------------------------------------------------
# 8080 is the documented default but is often taken, so probe upward rather
# than failing with a cryptic "address already in use".
find_free_port() {
  python3 - "$1" "$2" <<'PY'
import socket, sys
start, end = int(sys.argv[1]), int(sys.argv[2])
for port in range(start, end + 1):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
    print(port)
    break
else:
    sys.exit(f"No free port available between {start} and {end}.")
PY
}

step 'Finding a free port'
FRONTEND_PORT="$(find_free_port 8080 8099)" || exit 1
BACKEND_PORT="$(find_free_port 8000 8049)" || exit 1

export FRONTEND_PORT BACKEND_PORT
# Without this the container starts with an empty database, which makes the app
# look broken. The compose default is "false"; a first-run demo wants "true".
export SEED_DEMO_DATA_ON_STARTUP=true
export CORS_ORIGINS="http://localhost:$FRONTEND_PORT"

if [ "$FRONTEND_PORT" -ne 8080 ]; then
  good "UI will use port $FRONTEND_PORT (8080 was already in use)"
else
  good 'UI will use port 8080'
fi
good "API will use port $BACKEND_PORT"

# --- 3. Build and start -----------------------------------------------------
step 'Building images (first run takes several minutes)'
printf '    The backend image is ~1 GB: it bundles the RAG index and trained\n'
printf '    ML models. Please do not close this window.\n\n'

"${COMPOSE[@]}" up -d --build || die 'The stack failed to start. The output above should say why.'

# --- 4. Wait for health -----------------------------------------------------
step 'Waiting for the backend to become healthy'
HEALTH_URL="http://127.0.0.1:$BACKEND_PORT/api/v1/health/ready"
ready=""
for _ in $(seq 1 100); do
  if body="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null)" && printf '%s' "$body" | grep -q '"status":"ready"'; then
    ready="$body"
    break
  fi
  printf '.'
  sleep 3
done
printf '\n'

[ -n "$ready" ] || die "Backend did not become healthy in time. Check: ${COMPOSE[*]} logs --tail 60 backend"
good "Backend ready: $ready"

# The frontend is a static bundle behind nginx; a 200 means it is serving.
sleep 3
UI_URL="http://localhost:$FRONTEND_PORT"
if code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$UI_URL")" && [ "$code" = "200" ]; then
  good 'Frontend is serving'
else
  bad "Frontend answered HTTP ${code:-no response}"
fi

# --- 5. Open the browser ----------------------------------------------------
step 'Opening your browser'
if command -v open >/dev/null 2>&1; then open "$UI_URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$UI_URL" >/dev/null 2>&1
else printf '    Could not launch a browser - open %s yourself.\n' "$UI_URL"
fi

cat <<EOF

===========================================================
  The system is running.
===========================================================
  App        $UI_URL
  API docs   http://localhost:$BACKEND_PORT/docs
  Health     $HEALTH_URL

  Demo data is seeded: 3 farms, 6 fields, sensor telemetry, soil
  tests and a pending approval to review.

  To stop it later, run ./stop.sh

  Note: sensor readings are SIMULATED (there is no real probe
  hardware attached). Weather uses the live keyless Open-Meteo API
  when the field has coordinates, and falls back to clearly-labelled
  offline climatology when it does not.

EOF

read -r -p 'Press Enter to close (the app keeps running in Docker)' _
