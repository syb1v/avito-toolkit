# Avito Toolkit

Платформа анализа рынка Авито и массового управления собственными объявлениями:

- **Конкурентная разведка** — сбор публичной выдачи по поискам и профилям, история цен, прокси-метрики спроса.
- **Аналитика** — медиана/среднее/min/max/p25/p75 с IQR-отсечением выбросов, динамика, delisting-velocity.
- **AI-слой** — рыночные дайджесты и рекомендации цен через litellm (по умолчанию DeepSeek) со строгим JSON-выходом.
- **Массовое управление** (позже) — репрайсинг тысяч объявлений через Автозагрузку и официальный API с dry-run, аудитом и откатом.

> Публичный парсинг Авито нарушает пользовательское соглашение площадки. Проект собирает только публичные данные (цены, названия, статусы), не собирает персональные данные. Используйте ответственно и соблюдайте лимиты.

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| БД / очередь | PostgreSQL 16 + TimescaleDB, Redis 7 |
| Сбор | curl_cffi (Level 1), Patchright / Camoufox (Level 2, fallback) |
| Аналитика | polars, rapidfuzz, IQR-фильтрация |
| AI | litellm (DeepSeek по умолчанию), Pydantic Structured Outputs |
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Инфраструктура | Docker Compose, GitHub Actions |

## Быстрый старт

```bash
cp .env.example .env          # заполните DEEPSEEK_API_KEY при необходимости
docker compose up -d --build  # поднимет TimescaleDB, Redis, api, worker, scheduler, web
docker compose exec api alembic upgrade head
```

- API: http://localhost:8000/docs
- Дашборд: http://localhost:3000
- Healthcheck: `curl http://localhost:8000/healthz`

## Локальная проверка парсера (фаза 1)

Скачать страницу выдачи и распарсить без записи в БД:

```bash
cd backend
.venv/bin/python scripts/fetch_page.py \
  --url "https://www.avito.ru/moskva/telefony?q=iphone+15" \
  --out /tmp/avito.html --pages 2

# если страница отдаёт только SSR-оболочку или антибот-челлендж — рендер браузером:
.venv/bin/python scripts/fetch_page.py --browser \
  --url "https://www.avito.ru/moskva/telefony?q=iphone+15" --out /tmp/avito.html
```

Полный цикл с записью снапшотов:

```bash
docker compose up -d postgres redis          # из корня репозитория
cd backend
.venv/bin/alembic upgrade head
.venv/bin/dramatiq app.workers.tasks --processes 1 --threads 2 &
.venv/bin/uvicorn app.main:app --port 8000 &

# создать поиск и запустить обход
curl -s -X POST localhost:8000/api/v1/searches -H 'Content-Type: application/json' \
  -d '{"name":"iPhone 15","url":"https://www.avito.ru/moskva/telefony?q=iphone+15"}'
curl -s -X POST localhost:8000/api/v1/searches/<id>/crawl
curl -s localhost:8000/api/v1/searches/<id>/listings
```

Прокси включаются переменными `PROXY_ENABLED=true` и `PROXY_URL=...` — по умолчанию выключены.
Повторный обход не создаёт дубли: снапшоты пишутся только для новых объявлений и смены цены.
Если Авито отвечает страницей «Доступ ограничен: проблема с IP» — IP временно ограничен после
серии запросов: подождите, смените сеть или используйте прокси.



## Структура

```
backend/app/
├── api/            # FastAPI-роуты
├── collectors/     # SourceAdapter, транспорт (curl_cffi / браузеры), cookies в Redis
├── services/       # нормализация, аналитика (IQR, агрегаты), матчинг
├── integrations/   # официальный Avito API, Автозагрузка (XML/XSD)
├── ai/             # litellm-клиент, схемы, промпты
├── workers/        # фоновые задачи (dramatiq)
└── db/             # модели и сессии
migrations/         # Alembic, TimescaleDB hypertable
frontend/           # дашборд Next.js
docs/plan.md        # дорожная карта
```

## Команды разработки

```bash
make up / down / logs        # docker compose
make test / lint / typecheck # backend
make web-dev                 # frontend на http://localhost:3000
make migrate                 # alembic upgrade head
```

## Дорожная карта

| Фаза | Содержание | Статус |
|---|---|---|
| 0 | Каркас, инфраструктура, CI | готово |
| 1 | Коллектор Level 1 (curl_cffi), снапшоты цен | в работе |
| 2 | Аналитика + дашборд | |
| 3 | Level 2 fallback (Patchright/Camoufox) | |
| 4 | Матчинг + AI-дайджесты и рекомендации | |
| 5 | Официальный API: свои объявления, сравнение цен | |
| 6 | Автозагрузка: массовый репрайсинг, HITL, откат | |
| 7 | Splink/pgvector, MCP, вебхуки мессенджера | |

Подробный план — [docs/plan.md](docs/plan.md).

## Лицензия

[MIT](LICENSE)
