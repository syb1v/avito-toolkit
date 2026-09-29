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
| 0 | Каркас, инфраструктура, CI | текущая |
| 1 | Коллектор Level 1 (curl_cffi), снапшоты цен | |
| 2 | Аналитика + дашборд | |
| 3 | Level 2 fallback (Patchright/Camoufox) | |
| 4 | Матчинг + AI-дайджесты и рекомендации | |
| 5 | Официальный API: свои объявления, сравнение цен | |
| 6 | Автозагрузка: массовый репрайсинг, HITL, откат | |
| 7 | Splink/pgvector, MCP, вебхуки мессенджера | |

Подробный план — [docs/plan.md](docs/plan.md).

## Лицензия

[MIT](LICENSE)
