# План развития avito-toolkit

Платформа «Avito AI — аналитика рынка и массовое управление объявлениями».
Документ фиксирует архитектурные решения, аудит инструментов и дорожную карту.

## 1. Два контура данных

**Контур A — свои объявления (свои данные и публичный профиль).**
Официальный Business API Авито не используем: он платный/недоступен и относится
к внутренним API площадки. Источники: импорт JSON/CSV
(`POST /our-listings/import`), парсинг своего публичного профиля тем же коллектором
(`POST /our-listings/import-from-search/{id}`), ручной CRUD. Массовое редактирование
(фаза 6) — браузерная автоматизация с сессией продавца и safety-гейтом (dry-run,
preview, HITL, аудит, откат); референсы — GitHub-проекты (Duff89/parser_avito и др.).

**Контур B — рынок и конкуренты (публичный веб, API нет).**
Защита: Qrator/firewall + GeeTest, cookie-челленджи. Собираются только публичные
данные (цены, названия, статусы, позиции). Персональные данные (телефоны) не собираются.
Парсинг нарушает ToS площадки — эксплуатация на ответственность владельца.

## 2. Аудит инструментов (проверено)

| Инструмент | Статус | Роль |
|---|---|---|
| [Duff89/parser_avito](https://github.com/Duff89/parser_avito) | 751★, активен, без лицензии | Референс логики пагинации, cookies, прокси (код не копируем) |
| [Kaliiiiiiiiii-Vinyzu/patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) | 4.7k★, Apache-2.0 | Level 2: undetected-Playwright, drop-in |
| [daijro/camoufox](https://github.com/daijro/camoufox) | 12.2k★, MPL-2.0 | Level 2 fallback: анти-детект Firefox, тяжёлый — отдельный профиль compose |
| [yifeikong/curl_cffi](https://github.com/yifeikong/curl_cffi) | активен | Level 1: TLS/JA3/JA4-эмуляция, 90% трафика |
| [18studio/avito_python_api](https://github.com/18studio/avito_python_api) | MIT | SDK официального API (avito-py) |
| [MissiaL/avito-api](https://github.com/MissiaL/avito-api) | MIT (код) | OpenAPI-спек (238 путей) для генерации схем |
| [elchin92/avito-mcp](https://github.com/elchin92/avito-mcp) | MIT | Эталон безопасных масс-операций (read_only/guarded/full_access, dryRun, idempotency) |
| [ilyautov/marketplaces-mcp-ru](https://github.com/ilyautov/marketplaces-mcp-ru) | MIT | MCP-шлюз, safety-гейт read/write/destructive |
| [rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) | MIT | Матчинг заголовков (фаза 4) |
| [Splink](https://github.com/moj-analytical-services/splink) | MIT | Вероятностный record linkage (фаза 7) |
| [pgvector](https://github.com/pgvector/pgvector) | PostgreSQL | Семантический матчинг, rubert-tiny2 / bge-m3 (фаза 7) |
| [TimescaleDB](https://github.com/timescale/timescaledb) | Apache-2/TSL | Hypertable снапшотов, сжатие истории |
| [litellm](https://github.com/BerriAI/litellm) | MIT | Единый AI-клиент, structured outputs |

Исключено: `Bogdan-Z/avito-search-parser` — репозиторий не существует (была ссылка на поиск Google).
Поправка: `mickberrad659-sketch/Avito-Parser` написан на JavaScript, не Python — используется
только для разведки селекторов.
Решение владельца: официальный Business API Авито не используем (платный, недоступен, внутренний).
SDK/MCP-проекты оставлены в аудите только как справка по схемам; свои объявления ведём через
импорт и парсинг публичного профиля, массовые операции — через браузерные GitHub-подходы.

## 3. Архитектура

```
50 поисков/профилей ──► Collector
   Level 1 (90%): curl_cffi, TLS/JA3/JA4-эмуляция → JSON/HTML выдачи
   403/Qrator/JS-challenge ──► Level 2: Patchright/Camoufox → cookies → Redis
                               (привязка к выходному IP, TTL 12–24 ч)
                              │
                       Normalizer (дедуп avito_id, дифф цен и статусов)
                              │
        PostgreSQL+TimescaleDB (hypertable снапшотов, compression >90 дней)
        Redis (очереди dramatiq, cookies, token bucket rate limiter)
                              │
                       Analytics: IQR-фильтр, медиана/среднее/min/max/p25/p75,
                       delisting-velocity, market_analytics_daily
                              │
                       AI: litellm + Pydantic Structured Outputs
                       (DeepSeek по умолчанию, версии промптов, llm_runs, кэш)
                              │
                       FastAPI + Next.js дашборд

Контур A (фазы 5–6):
Импорт JSON/CSV и публичный профиль → `our_listings` → матчинг с рынком и дельта
к медиане; массовое редактирование — браузерный воркер с сессией продавца,
dry-run/preview, HITL >10%, журнал аудита и откат по снапшотам «до/после».
```

Ключевой интерфейс — `SourceAdapter`. Прокси-модуль присутствует с фазы 1, но по
умолчанию выключен (`PROXY_ENABLED=false`).

## 4. Модель данных

- `searches` — реестр поисков (URL, фильтры JSONB, расписание, приоритет).
- `sellers`, `listings` — продавцы и объявления (текущая цена, first/last seen, статус).
- `search_listings` — m:n выдача ↔ поиск, last_position.
- `listing_snapshots` — hypertable `(search_id, listing_id, recorded_at)`: цена, позиция, бейджи.
  `position_index` привязан к поиску, поэтому `search_id` входит в ключ.
- `market_analytics_daily` — агрегаты дня: counts, min/max/median/p25/p75, avg_lifetime_days.
- `product_market_matches` — сопоставление наших SKU с рыночными объявлениями (score, статус).
- `jobs`, `llm_runs`, `alerts`, `audit_log` — задания, учёт токенов/стоимости, алерты, аудит.
- Фаза 6: `CHECK (price >= min_price)` + trigger, снапшоты «до/после» для отката.

## 5. Алгоритмы

**IQR-отсечение выбросов:** `IQR = Q3 − Q1`, границы `[max(0, Q1 − 1.5·IQR), Q3 + 1.5·IQR]`,
цены вне диапазона не участвуют в медиане.

**Стратегии репрайсинга:** `undercut_p25` (P25 − 1%), `match_median`, `premium_p75`,
`keep_current`; clamp по `[min_price, max_price]`, лимит шага 5%, HITL при дельте >10%.

**Прокси-спрос:** `delisted_7d / active_total > 0.35` → цена ближе к P75;
слабое выбывание и рост времени жизни → к P25. Реальные продажи конкурентов Авито
не публикует — используются прокси-метрики (время жизни, скорость вымывания, новые за день).

## 6. AI-слой

litellm + `response_format` (Pydantic-схема), temperature 0.1, системный промпт
«коммерческий директор и ценовой аналитик». Версии промптов в БД, лог `llm_runs`
(токены/стоимость), кэш по хэшу входа, вызов только при изменении данных.

## 7. Надёжность и безопасность

- Redis token bucket на домен публичного сбора — защита от 429.
- Согласованные UA + `Sec-Ch-Ua`/Client Hints с фингерпринтом транспорта.
- min_price trigger; dry-run/preview; идемпотентные ключи; аудит; откат.

## 8. Дорожная карта

| Фаза | Содержание | Критерий готовности | Статус |
|---|---|---|---|
| 0 | Каркас, compose, БД, CI | `docker compose up`, тесты/lint зелёные | готово |
| 1 | Collector Level 1 + браузерный fallback, снапшоты, планировщик | 5 поисков собираются без дублей | готово |
| 2 | Аналитика (IQR, daily) + дашборд | метрики корректны на тест-данных | готово |
| 3 | Level 2: Patchright + Camoufox (профиль) | 403 → автополучение cookies | Patchright + постоянный профиль (browser-login); Camoufox — по потребности |
| 4 | Матчинг + AI-дайджесты и рекомендации + алерты | отчёт по поиску в UI | готово |
| 5 | Импорт своих объявлений (JSON + из поиска/профиля), сравнение с рынком | дельта к медиане, алерты | готово |
| 6 | Массовое редактирование через браузерную сессию продавца (dry-run, HITL, аудит, откат) | батч 100 SKU с dry-run и откатом | следующая |
| 7 | Splink/pgvector, MCP, вебхуки мессенджера + LLM-автоответы | по потребности | |
