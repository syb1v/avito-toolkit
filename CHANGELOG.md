# Changelog

Все значимые изменения проекта документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
проект следует [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

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

[Unreleased]: https://github.com/syb1v/avito-toolkit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/syb1v/avito-toolkit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/syb1v/avito-toolkit/releases/tag/v0.1.0
