#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  NaviSound — Local Docker Compose deployment
#
#  Usage:
#    chmod +x deploy/local.sh
#    ./deploy/local.sh          # build & start
#    ./deploy/local.sh down     # stop everything
#    ./deploy/local.sh logs     # tail logs
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

COMPOSE_FILE="config/docker-compose.yml"
ACTION="${1:-up}"

case "${ACTION}" in
  up|start)
    echo "══ NaviSound — Building & starting all services ══"
    docker compose -f "${COMPOSE_FILE}" up --build -d
    echo ""
    echo "✅  All services running!"
    echo "   Frontend:  http://localhost"
    echo "   Gateway:   ws://localhost:3000"
    echo "   Backend:   http://localhost:8000"
    echo "   Postgres:  localhost:5432"
    echo "   Redis:     localhost:6379"
    echo ""
    echo "   Logs:  docker compose -f ${COMPOSE_FILE} logs -f"
    echo "   Stop:  ./deploy/local.sh down"
    ;;
  down|stop)
    echo "══ NaviSound — Stopping all services ══"
    docker compose -f "${COMPOSE_FILE}" down
    ;;
  logs)
    docker compose -f "${COMPOSE_FILE}" logs -f
    ;;
  restart)
    docker compose -f "${COMPOSE_FILE}" down
    docker compose -f "${COMPOSE_FILE}" up --build -d
    ;;
  ps|status)
    docker compose -f "${COMPOSE_FILE}" ps
    ;;
  *)
    echo "Usage: $0 {up|down|logs|restart|status}"
    exit 1
    ;;
esac
