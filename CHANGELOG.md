# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

## [0.4.0] - 2026-09-29

## [0.3.0] - 2026-09-29

### Добавлено

- Аналитический сервис: пересчёт дневных агрегатов (`market_analytics_daily`) и
  сводка рынка — цены с IQR-фильтрацией (медиана/средняя/P25/P75/min/max),
  новые и снятые объявления, вымывание за 7 дней, средний срок жизни.
- API: `GET /api/v1/searches/{id}/summary` и `GET /api/v1/searches/{id}/history`.
- Автоматический пересчёт агрегатов после каждого обхода и ночной job планировщика.
- Дашборд: список поисков, страница поиска с карточками метрик,
  графиком медианы/P25/P75 (recharts) и таблицей выдачи.

### Исправлено

- Пустые значения переменных окружения (например, `AVITO_USER_ID=""` из docker-compose)
  больше не ломают запуск backend: пустые строки приводятся к `None`.
- В Docker веб-сервис обращается к API по внутреннему адресу `http://api:8000`,
  а ссылка для браузера остаётся `http://localhost:8000`.

## [0.2.0] - 2026-09-29

### Добавлено

- Коллектор Level 1: обход поисковой выдачи через curl_cffi с TLS-эмуляцией,
  пагинация, дедупликация по `avito_id`, задержки между запросами.
- Redis rate limiter (fixed-window) на домен источника.
- Парсер выдачи: встроенный `__initialData__` JSON и DOM-fallback по `data-marker`,
  извлечение ID, цены, продавца, VIP/выделения.
- Хранение: upsert объявлений, продавцов и связи «поиск ↔ объявление»,
  снапшоты цен только для новых объявлений и изменений цены,
  пометка `gone` для исчезнувших из выдачи.
- Воркер `crawl_search` (dramatiq), планировщик cron на каждый поиск (APScheduler),
  API-эндпоинты `POST /api/v1/searches/{id}/crawl` и `GET /api/v1/searches/{id}/listings`.
- Level 2: рендер через Patchright (undetected Chromium) и `HybridTransport`
  с автоматическим фолбэком на браузер при антибот-челлендже или пустой SSR-оболочке.
- Локальный скрипт `backend/scripts/fetch_page.py` (флаг `--browser`) для проверки
  парсинга без БД и Redis.
- Тесты парсера, rate limiter (fakeredis) и гибридного транспорта — 32 теста.

## [0.1.0] - 2026-09-29

### Добавлено

- Каркас проекта: FastAPI, SQLAlchemy 2.0 (11 моделей), Alembic-миграция
  с TimescaleDB hypertable для снапшотов, Docker Compose (TimescaleDB, Redis,
  api, worker, scheduler, web), GitHub Actions CI.
- Аналитика: IQR-отсечение выбросов, перцентили (p25/p50/p75), дневные агрегаты,
  стратегии репрайсинга с ограничением шага и порогом ручного подтверждения.
- AI-слой: litellm со Structured Outputs (DeepSeek по умолчанию), версии промптов,
  схемы рекомендаций цены и рыночного дайджеста.
- Коллектор-каркас: интерфейс `SourceAdapter`, cookie store в Redis,
  конфигурация прокси (по умолчанию выключены).
- Дашборд Next.js 16 + Tailwind 4 со статусом API и дорожной картой.
- Документация: README, `docs/plan.md`, `.env.example`, MIT-лицензия.

[Unreleased]: https://github.com/syb1v/avito-toolkit/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/syb1v/avito-toolkit/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/syb1v/avito-toolkit/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/syb1v/avito-toolkit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/syb1v/avito-toolkit/releases/tag/v0.1.0
