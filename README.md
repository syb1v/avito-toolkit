# Avito Toolkit

Платформа анализа рынка Авито и массового управления собственными объявлениями:

- **Конкурентная разведка** — сбор публичной выдачи по поискам и профилям, история цен, прокси-метрики спроса.
- **Аналитика** — медиана/среднее/min/max/p25/p75 с IQR-отсечением выбросов, динамика, delisting-velocity.
- **AI-слой** — рыночные дайджесты и рекомендации цен через litellm (по умолчанию DeepSeek) со строгим JSON-выходом.
- **Умная фильтрация (AI-модерация)** — отсев копий/реплик/приманок и нерелевантных карточек до расчёта статистики: бесплатные правила + DeepSeek батчами (~$0.001–0.002 за прогон). Честный разбор точности — [docs/accuracy.md](docs/accuracy.md).
- **Управление поисками в UI** — добавление/редактирование позиций, include-группы и стоп-слова (exclude), фильтры по городам, приоритет, cron, аккаунт; обход без лимита страниц (0 = все, до пустой выдачи).
- **Полный контроль выдачи** — сортировка по цене/позиции/новизне, чипы по городам и категориям, ручное исключение любого объявления из расчёта (обратимо) с прозрачными причинами: стоп-слово, регион, ручная метка.
- **Аккаунты и cookies** — несколько профилей Chromium, загрузка cookies из браузера или вставкой в UI, проверка доступа, привязка к поискам, автозамок профиля. Гайд — [docs/accounts.md](docs/accounts.md).
- **Уход за аккаунтами** — дневной лимит активности, автоматический «отдых» после челленджа/429, мягкий прогрев по расписанию и ручные кнопки «Прогреть/Отдохнуть/Разбудить»; гайд — [docs/account-care.md](docs/account-care.md).
- **Алерты** — подтверждение и очистка (по поиску или все).
- **Массовое управление** (позже) — репрайсинг тысяч объявлений через браузерную сессию продавца с dry-run, аудитом и откатом.

> Публичный парсинг Авито нарушает пользовательское соглашение площадки. Проект собирает только публичные данные (цены, названия, статусы), не собирает персональные данные. Используйте ответственно и соблюдайте лимиты.

## Продакшен на сервере (Docker + nginx + Basic Auth)

Панель развёрнута на `http://150.241.87.50/` (логин/пароль Basic Auth хранятся в
`PANEL_USER`/`PANEL_PASSWORD` в `.env` на сервере; `/healthz` открыт для деплой-чека).
API за тем же доменом: `/api/...`, Swagger: `/docs`.

- Прод-стек: `docker-compose.prod.yml` — наружу только 80 (nginx), БД/Redis/API/фронт
  не публикуются; фронт собирается с пустым `NEXT_PUBLIC_API_URL` (относительные
  `/api` через nginx).
- Установка/обновление на сервере: `bash /opt/avito-toolkit/deploy/deploy.sh`
  (git pull → Basic Auth → build → миграции → up → healthcheck).
- CI/CD: `.github/workflows/deploy.yml` деплоит по **release published** и вручную
  (`gh workflow run deploy.yml`). Секреты репозитория: `DEPLOY_HOST`, `DEPLOY_USER`,
  `DEPLOY_SSH_KEY` (ed25519-ключ, публичная часть в `/root/.ssh/authorized_keys`).
- **Важно:** сервер — датацентр, Авито режет такие IP (403). Панель/аналитика
  работают, но обход с сервера пойдёт только через резидентные/мобильные прокси,
  закреплённые за аккаунтом (кнопка «Прокси» в «Аккаунтах»). Иначе держите воркер
  на домашней машине с личным IP.

## Правки объявлений (фаза 6)

Страница **«Правки»**: система считает целевые цены по рынку, вы одобряете изменения
(шаг ≤5%, всё, что больше 10% — только вручную), и правка выполняется **в кабинете
продавца через браузер**: открыть объявление, изменить цену, сохранить, проверить,
сделать скриншот. Есть журнал «до/после» и откат. Официальный API Авито для этого
не используется — он не даёт нужного управления объявлениями.

Режимы: `SELLER_EDIT_MODE=dry_run` (по умолчанию — только журнал, на Авито ничего
не меняется) и `live` (реальные правки; нужен аккаунт-продавец с cookies).
Для live-правок у SKU должна быть ссылка/ID объявления (импорт своего профиля).

## Telegram-бот

Бот **@avitotoolkitbot**: вход по логину/паролю (`TELEGRAM_LOGIN`/`TELEGRAM_PASSWORD`
в `.env`), сессия 30 дней. Команды: `/status`, `/searches`, `/crawl <id|название>`,
`/alerts`, `/digest <id|название>`, `/logout`. Присылает новые уведомления
(включая «воркер не отвечает»). Запускается сервисом `telegram` в docker compose.

## Управление прокси из UI

Прокси хранятся в БД и управляются прямо в панели «Прокси»: добавить (по одному
в строке, поддерживаются `http://user:pass@host:port`, `host:port:user:pass`,
`socks5://...`), выключить/включить, удалить. `PROXY_LIST` из `.env` используется
как первичный сид. Для аккаунтов работает закрепление прокси (sticky).

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

Полный серверный стек (всё в Docker):

```bash
cp .env.example .env          # заполните DEEPSEEK_API_KEY при необходимости
docker compose up -d --build  # поднимет TimescaleDB, Redis, api, worker, scheduler, web
docker compose exec api alembic upgrade head
```

- API: http://localhost:8000/docs
- Дашборд: http://localhost:3000
- Healthcheck: `curl http://localhost:8000/healthz`

Локальный дев-стек (как на этой машине: Docker только postgres/redis/worker,
а API/планировщик/фронт — из venv/node) — одной командой:

```bash
make start     # docker infra + uvicorn :8000 + scheduler + next dev :3000 (tmux)
make status    # что запущено, healthcheck, пути к логам
make stop      # остановить
```

После перезагрузки машины достаточно `make start`: postgres/redis/worker имеют
`restart: unless-stopped`, остальное поднимается скриптом `scripts/dev.sh`
(логи — `/tmp/avito-*.log`).

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

Прокси задаются в `PROXY_LIST` и включаются для движка `PROXY_ENABLED=true`. Пока флаг
выключен, панель «Прокси» всё равно проверяет пул (`POST /api/v1/proxies/check?avito=true`),
чтобы видеть, жив ли канал и пускает ли Авито: датацентр-прокси часто отвечают
`403 / доступ ограничен` — это детект IP, а не поломка прокси.
Повторный обход не создаёт дубли: снапшоты пишутся только для новых объявлений и смены цены.

**Про «Доступ ограничен: проблема с IP».** Это заглушка антибот-фаервола Авито (hCaptcha),
а не блокировка самого IP: обычный браузер на том же IP работает, потому что у него есть
доверенные cookies. Автоматизированная сессия стартует «чистой», поэтому фаервол её
проверяет. Вторая важная деталь: Авито отдаёт выдачу только в «видимом» браузере —
в headless-режиме приходит пустая оболочка без объявлений. Один раз перенесите доверие
из своего браузера:

```bash
make cookies                  # cookies из Brave (BROWSER=chrome/chromium/... — на выбор)
# или вручную: make browser-login  (окно, пройдите проверку)
# .env: BROWSER_USER_DATA_DIR=.browser-profile, BROWSER_HEADLESS=false
```

Скрипт `make cookies` сам читает cookies `avito.ru` из браузера, пишет их в чистый
профиль автоматизации и проверяет выдачу (ждём 50 объявлений). Если Авито снова начнёт
показывать челлендж — повторите `make cookies`: сессия в вашем браузере довереннее.

На сервере в Docker это уже учтено: браузерный воркер запускается под Xvfb
(`BROWSER_HEADLESS=false`), а в dev-режиме (`make up-dev`) использует **тот же профиль**
`backend/.browser-profile`, куда пишет `make cookies`. В prod-образе профиль лежит
в томе `browserdata`. Всегда используйте свежий Chromium канала `chromium`
(не headless-shell). Для сервера дополнительно рекомендуются резидентные прокси.

## Полностью автоматический режим (реальные данные)

Тестовые данные не нужны: загрузите свои поиски/профили — дальше всё идёт по расписанию.

1. Запустите стек. В Docker воркер собирается с браузером (Patchright + Chromium),
   первая сборка долгая:
   ```bash
   docker compose up -d --build
   ```
   Для ноутбука можно без браузерного образа: `docker compose up -d postgres redis api scheduler web`
   и воркер из venv (там Chromium уже установлен): `make worker-local`.

2. Один раз перенесите cookies из своего браузера (Авито в нём работает):
   ```bash
   make cookies              # по умолчанию из Brave; BROWSER=chrome|chromium|firefox|...
   # запасной вариант: make browser-login и пройти проверку в окне
   ```
   и добавьте в `.env`: `BROWSER_USER_DATA_DIR=.browser-profile` (в dev-стеке это уже
   так). Cookies сохранятся, воркер будет переиспользовать их в автоматических обходах.

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

5. Для сервера обязательно резидентные прокси: `PROXY_ENABLED=true` и
   `PROXY_LIST=http://user:pass@host:port,...` — иначе поток запросов с одного IP
   приведёт к антибот-проверкам Авито. Датацентр-прокси Авито обычно режет (403,
   «доступ ограничен»): панель «Прокси» покажет это как «Авито блокирует», и движок
   останется на прямом канале с cookies.

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
- [docs/account-care.md](docs/account-care.md) — уход за аккаунтами: прогрев,
  «отдых», лимиты, признаки проблем и что делать.
- [docs/accounts.md](docs/accounts.md) — аккаунты: `make account-add`/`account-cookies`,
  загрузка cookies через UI, привязка к поискам, перенос на сервер.
- [docs/authorization.md](docs/authorization.md) — «прогретые» аккаунты: `make cookies`,
  browser-login, импорт cookies, Xvfb/Docker, диагностика антибота.
- [docs/accuracy.md](docs/accuracy.md) — насколько точны фильтры, AI-модерация и
  расчёты аналитики; как проверять самому.
- [docs/plan.md](docs/plan.md) — план развития, журнал проверок, известные ограничения.
- [CHANGELOG.md](CHANGELOG.md) — история версий.

## Известные ограничения

- Авито отдаёт результаты поиска только «видимому» браузеру: headless-режим возвращает
  пустую оболочку. Level 2 работает в headed-режиме (на сервере — под Xvfb).
- Страницы можно не ограничивать (`CRAWL_MAX_PAGES_PER_RUN=0`, `max_pages=0` у поиска):
  обход идёт до пустой выдачи. При троттлинге (429) срабатывает CrawlGuard — кулдаун
  по поиску и пауза после серии блокировок; собранное сохраняется. Паузы между
  страницами (`CRAWL_DELAY_*`) стоит увеличить при больших объёмах.
- Браузерный транспорт работает через HTTP/HTTPS-прокси (Chromium не поддерживает
  авторизацию в SOCKS5); SOCKS5 доступен HTTP-транспорту. Пул проверен на живом
  провайдере: канал/авторизация работают, но датацентр-диапазоны Авито отдаёт `403`
  («доступ ограничен») — панель показывает это отдельной меткой «Авито блокирует»,
  а не кулдауном; для обхода нужны резидентные/мобильные IP.
- «Чистый» профиль получает hCaptcha: лечится `make cookies` (cookies из вашего
  Brave/Chrome), `make browser-login` или `import_cookies.py`.
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
