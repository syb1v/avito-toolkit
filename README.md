# Avito Toolkit

Платформа анализа рынка Авито и массового управления собственными объявлениями:

- **Конкурентная разведка** — сбор публичной выдачи по поискам и профилям, история цен, прокси-метрики спроса.
- **Аналитика** — медиана/среднее/min/max/p25/p75 с IQR-отсечением выбросов, динамика, delisting-velocity.
- **AI-слой** — рыночные дайджесты и рекомендации цен через litellm (по умолчанию DeepSeek) со строгим JSON-выходом.
- **Умная фильтрация (AI-модерация)** — отсев копий/реплик/приманок и нерелевантных карточек до расчёта статистики: бесплатные правила + DeepSeek батчами (~$0.001–0.002 за прогон).
- **Массовое управление** (позже) — репрайсинг тысяч объявлений через браузерную сессию продавца с dry-run, аудитом и откатом.

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

**Про «Доступ ограничен: проблема с IP».** Это заглушка антибот-фаервола Авито (hCaptcha),
а не блокировка самого IP: обычный браузер на том же IP работает, потому что у него есть
доверенные cookies. Автоматизированная сессия стартует «чистой», поэтому фаервол её
проверяет. Вторая важная деталь: Авито отдаёт выдачу только в «видимом» браузере —
в headless-режиме приходит пустая оболочка без объявлений. Поэтому:

```bash
make browser-login            # один раз: окно, пройдите проверку (профиль сохранится)
# .env: BROWSER_USER_DATA_DIR=.browser-profile, BROWSER_HEADLESS=false
```

На сервере в Docker это уже учтено: браузерный воркер запускается под Xvfb
(`xvfb-run`) с `BROWSER_HEADLESS=false`, профиль лежит в томе `browserdata`.
Всегда используйте свежий Chromium канала `chromium` (не headless-shell).
После прогрева профиля Level 2 (воркер/скрипты) переиспользует cookies;
для сервера дополнительно рекомендуются резидентные прокси.

## Полностью автоматический режим (реальные данные)

Тестовые данные не нужны: загрузите свои поиски/профили — дальше всё идёт по расписанию.

1. Запустите стек. В Docker воркер собирается с браузером (Patchright + Chromium),
   первая сборка долгая:
   ```bash
   docker compose up -d --build
   ```
   Для ноутбука можно без браузерного образа: `docker compose up -d postgres redis api scheduler web`
   и воркер из venv (там Chromium уже установлен): `make worker-local`.

2. Один раз прогрейте браузерный профиль (пройдите проверку Авито):
   ```bash
   make browser-login
   ```
   и добавьте в `.env`: `BROWSER_USER_DATA_DIR=.browser-profile`. Cookies сохранятся,
   воркер будет переиспользовать их в автоматических обходах.

3. Загрузите реальные поиски (фильтры, названия, ссылки на профили конкурентов):
   ```bash
   cp searches.example.json searches.json   # вставьте свои URL
   make import-searches file=searches.json
   # или POST /api/v1/searches/import с тем же JSON
   ```

   Свои SKU для сравнения цен: `make import-skus file=skus.json` (шаблон
   `skus.example.json`) или одной командой из своего профиля:
   `make import-profile url="https://www.avito.ru/user/XXXX/profile"`,
   затем `POST /api/v1/our-listings/match-all`. Подробнее —
   [docs/user-guide.md](docs/user-guide.md).

4. Дальше автоматически: планировщик по cron (по умолчанию каждые 30 минут) ставит обход →
   воркер собирает выдачу (HTTP, при блокировке — браузер) → снапшоты цен → дневные агрегаты →
   матчинг наших SKU → алерты. AI-дайджест — кнопкой в UI (нужен `DEEPSEEK_API_KEY`).

5. Для сервера обязательно прокси: `PROXY_ENABLED=true`, `PROXY_URL=http://user:pass@host:port` —
   иначе поток запросов с одного IP приведёт к антибот-проверкам Авито.

Формат `searches.json`:
```json
[
  {"name": "iPhone 15 Москва", "url": "https://www.avito.ru/moskva/telefony?q=iphone+15", "schedule_cron": "*/30 * * * *", "priority": 100},
  {"name": "Профиль конкурента", "url": "https://www.avito.ru/user/12345/profile"}
]
```

Свои объявления для сравнения цен: импорт SKU (`POST /api/v1/our-listings/import`) или
перенос из спарсенного профиля (`POST /api/v1/our-listings/import-from-search/{id}`),
затем `POST /api/v1/our-listings/match-all`. Страница: `/our-listings`.




## Структура

```
backend/app/
├── api/            # FastAPI-роуты
├── collectors/     # SourceAdapter, транспорт (curl_cffi / браузеры), cookies в Redis
├── services/       # нормализация, аналитика (IQR, агрегаты), матчинг, импорт наших SKU
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

## Версионирование и релизы

Проект следует [Semantic Versioning](https://semver.org/lang/ru/), история изменений —
[CHANGELOG.md](CHANGELOG.md) в формате Keep a Changelog. Единый источник версии —
`backend/app/__init__.py` (pyproject подхватывает её автоматически);
`frontend/package.json` и CHANGELOG синхронизируются скриптом.

```bash
make bump part=minor                          # 0.2.0 -> 0.3.0, финализирует Unreleased
git add -A && git commit -m "chore(release): v0.3.0"
make tag                                      # тег v0.3.0 -> GitHub Release из CHANGELOG
```

CI проверяет согласованность версий (`scripts/check_version_consistency.py`),
push тега `v*` публикует GitHub Release с секцией из CHANGELOG.

## Документация

- [docs/user-guide.md](docs/user-guide.md) — как пользоваться панелью: метрики,
  рекомендации, алерты, автоматика.
- [docs/authorization.md](docs/authorization.md) — «прогретые» аккаунты: browser-login,
  импорт cookies, Xvfb/Docker, диагностика антибота.
- [docs/plan.md](docs/plan.md) — план развития, журнал проверок, известные ограничения.
- [CHANGELOG.md](CHANGELOG.md) — история версий.

## Известные ограничения

- Авито отдаёт результаты поиска только «видимому» браузеру: headless-режим возвращает
  пустую оболочку. Level 2 работает в headed-режиме (на сервере — под Xvfb).
- После ~10 страниц подряд включается троттлинг (429) — обход корректно останавливается
  и сохраняет собранное. Для больших объёмов нужны резидентные прокси/ротация.
- «Чистый» профиль получает hCaptcha: лечится `make browser-login` или импортом cookies
  из обычного браузера (`scripts/import_cookies.py`).
- Живой SERP ротируется между обходами — единичные «новые/ушедшие» лоты это динамика,
  а не дубли: идемпотентность гарантируется на уровне `(listing_id, цена)`.
- Живой тест с резидентным прокси не выполнен (нет доступа к провайдеру).
- AI-дайджест и рекомендации требуют `DEEPSEEK_API_KEY` (без него API отдаёт 409).

## Дорожная карта

| Фаза | Содержание | Статус |
|---|---|---|
| 0 | Каркас, инфраструктура, CI | готово |
| 1 | Коллектор (браузер-first + HTTP), снапшоты цен, планировщик | готово: реальный прогон — 443 лота |
| 2 | Аналитика (IQR, daily) + дашборд | готово |
| 3 | Level 2 hardening: профиль, капча, Xvfb | готово |
| 4 | Матчинг + AI-дайджесты и рекомендации + алерты | готово |
| 5 | Импорт своих объявлений + сравнение с рынком | готово |
| 6 | Массовое редактирование через браузерную сессию (dry-run, HITL, откат) | отложена |
| 7 | Splink/pgvector, MCP, вебхуки мессенджера | опционально |

**Текущий фокус** — проработка и тестирование уже собранного: регрессия парсера на
реальных фикстурах, e2e-смоук сбора, сверка аналитики, устойчивость к 429/капче,
smoke очередей и UI. Чеклист и остатки плана — [docs/plan.md](docs/plan.md)
(разделы 9–11).

Подробный план — [docs/plan.md](docs/plan.md).

## Лицензия

[MIT](LICENSE)
