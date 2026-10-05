#!/usr/bin/env bash
# Деплой на сервер: git pull → Basic Auth → сборка → миграции → запуск.
# Вызывается из GitHub Actions (.github/workflows/deploy.yml) или вручную:
#   bash /opt/avito-toolkit/deploy/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

echo "== git: обновление кода =="
git fetch --all --tags --prune
git checkout main
git pull --ff-only

echo "== Basic Auth (deploy/.htpasswd из .env) =="
set -a
# shellcheck disable=SC1091
. ./.env
set +a
# файл может быть каталогом, если раньше bind-mount создал его до первого запуска
if [ -d deploy/.htpasswd ]; then
    rm -rf deploy/.htpasswd
fi
if [ -n "${PANEL_PASSWORD:-}" ]; then
    HASH="$(openssl passwd -apr1 "$PANEL_PASSWORD")"
    printf '%s:%s\n' "${PANEL_USER:-admin}" "$HASH" > deploy/.htpasswd
else
    printf '%s:!\n' "${PANEL_USER:-admin}" > deploy/.htpasswd
    echo "WARN: PANEL_PASSWORD не задан в .env — вход в панель закрыт" >&2
fi
chmod 600 deploy/.htpasswd

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
# bind-mount конфигов: пересоздаём nginx, чтобы гарантированно подхватить их
"${COMPOSE[@]}" up -d --force-recreate nginx

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
