#!/usr/bin/env bash
# Управление локальным дев-стеком Avito Toolkit.
#
#   scripts/dev.sh start    — postgres/redis/worker (docker) + API/scheduler/web (tmux)
#   scripts/dev.sh stop     — остановить хост-процессы (API/scheduler/web) и воркер
#   scripts/dev.sh status   — что запущено, healthcheck, где логи
#
# Логи: /tmp/avito-api.log, /tmp/avito-scheduler.log, /tmp/avito-web.log
# Хост-процессы живут в tmux-сессиях avito-api / avito-scheduler / avito-web
# и переживают закрытие терминала.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
COMPOSE_BASE=(docker compose -f "$ROOT/docker-compose.yml")
COMPOSE_DEV=(docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.dev.yml")
NODE_LD="${NODE_LD:-$HOME/.local/lib/node-compat}"

export PLAYWRIGHT_BROWSERS_DIR="${PLAYWRIGHT_BROWSERS_DIR:-$HOME/.cache/ms-playwright}"
export HOST_UID="${HOST_UID:-$(id -u)}"
export HOST_GID="${HOST_GID:-$(id -g)}"

ensure_tmux() {
  if ! command -v tmux >/dev/null 2>&1; then
    echo "FAIL: нужен tmux (sudo apt install tmux)" >&2
    exit 1
  fi
}

start_tmux_session() {
  local name="$1"
  shift
  tmux kill-session -t "$name" 2>/dev/null || true
  tmux new-session -d -s "$name" "$*"
}

start() {
  ensure_tmux
  echo "== Docker: postgres, redis =="
  "${COMPOSE_BASE[@]}" up -d postgres redis
  echo "== Docker: worker (Xvfb + Chromium) =="
  "${COMPOSE_DEV[@]}" up -d --no-build worker
  echo "== API (uvicorn :8000) =="
  start_tmux_session avito-api \
    "cd '$BACKEND' && exec .venv/bin/uvicorn app.main:app --port 8000 >> /tmp/avito-api.log 2>&1"
  echo "== Планировщик =="
  start_tmux_session avito-scheduler \
    "cd '$BACKEND' && exec .venv/bin/python -m app.scheduler >> /tmp/avito-scheduler.log 2>&1"
  echo "== Frontend (next dev :3000) =="
  if [ -d "$NODE_LD" ]; then
    start_tmux_session avito-web \
      "cd '$FRONTEND' && exec env LD_LIBRARY_PATH='$NODE_LD' npm run dev >> /tmp/avito-web.log 2>&1"
  else
    start_tmux_session avito-web \
      "cd '$FRONTEND' && exec npm run dev >> /tmp/avito-web.log 2>&1"
  fi
  sleep 6
  status
}

stop() {
  echo "== Останавливаю хост-процессы =="
  for session in avito-api avito-scheduler avito-web; do
    tmux kill-session -t "$session" 2>/dev/null && echo "  $session: stop" || true
  done
  echo "== Останавливаю воркер =="
  "${COMPOSE_DEV[@]}" stop worker >/dev/null
  echo "postgres/redis оставлены запущенными (docker stop avito-toolkit-postgres-1 avito-toolkit-redis-1)"
}

status() {
  echo "== tmux =="
  tmux ls 2>/dev/null || echo "  нет сессий"
  echo "== docker =="
  docker ps --format '  {{.Names}}: {{.Status}}' | grep avito || echo "  нет контейнеров"
  echo "== API =="
  curl -s -m 5 http://localhost:8000/healthz || echo "  API недоступен"
  echo
  echo "== Frontend =="
  curl -s -o /dev/null -m 10 -w "  http://localhost:3000 → %{http_code}\n" \
    http://localhost:3000/ || echo "  frontend недоступен"
  echo "Логи: /tmp/avito-api.log, /tmp/avito-scheduler.log, /tmp/avito-web.log"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *)
    echo "usage: scripts/dev.sh {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
