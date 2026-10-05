#!/usr/bin/env bash
# Деплой на сервер: git pull → сборка → миграции → запуск.
# Вызывается из GitHub Actions (.github/workflows/deploy.yml) или вручную:
#   bash /opt/avito-toolkit/deploy/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "== git: обновление кода =="
git fetch --all --tags --prune
git checkout main
git pull --ff-only

echo "== сборка образов =="
"${COMPOSE[@]}" build

echo "== поднимаю postgres/redis =="
"${COMPOSE[@]}" up -d --wait postgres redis

echo "== миграции БД =="
for attempt in 1 2 3 4 5; do
    if "${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head; then
        break
    fi
    if [ "$attempt" = 5 ]; then
        echo "FAIL: миграции не применились" >&2
        exit 1
    fi
    echo "миграции: БД ещё не готова, повтор $attempt"
    sleep 5
done

echo "== запуск стека =="
"${COMPOSE[@]}" up -d

echo "== статус =="
"${COMPOSE[@]}" ps

echo "== healthcheck =="
for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if curl -fsS -m 5 http://localhost/healthz >/dev/null 2>&1; then
        echo "OK: панель отвечает"
        exit 0
    fi
    sleep 3
done
echo "FAIL: healthcheck не прошёл" >&2
exit 1
