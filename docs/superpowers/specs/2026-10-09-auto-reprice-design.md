# Авто-правки цен в «Наши объявления» — дизайн

Дата: 2026-10-09. Статус: одобрено (чат). Релиз: v0.29.0.

## Цель

Цены своих объявлений меняются сами на основе системы (медиана/P25/P75, матчи,
стратегия), а не только показываются рекомендации. Страница «Правки» удаляется,
управление и история переезжают в карточку SKU в «Наших объявлениях». К каждой
правке — краткая AI-сводка «почему меняем».

## Не-цели

- Не редактируем ничего кроме цены (заголовок/описание/фото не трогаем).
- Не делаем отдельный движок правил: переиспользуем `ListingEdit` + `seller.apply_price_edit`.
- Нет мгновенных правок после каждого обхода — только ночное задание.

## Поток данных

1. Планировщик по cron `REPRICE_AUTO_CRON` (по умолчанию `0 0 * * *` UTC ≈ 03:00 МСК)
   ставит dramatiq-задачу `auto_reprice`.
2. Задача читает Redis-тумблер `reprice:auto` = `{"enabled": bool, "live": bool}`.
   Если выключено — выход. `live` возможен только при `SELLER_EDIT_MODE=live` в env
   (двойная защита).
3. `build_recommendations()` → детерминированные цели (`build_price_target`):
   шаг ≤ `REPRICE_MAX_STEP_PCT` (5%), не ниже себестоимости, стратегия из
   `suggest_strategy` (undercut_p25 / match_median / premium_p75 / keep_current).
4. Отбор SKU: активный, есть `avito_item_id` и `avito_url`, нет открытой правки
   (`draft/approved/applying/reverting`), |Δ| по clamped-цене > 0 (пустые не создаём).
5. Создание `ListingEdit`: `status=approved`, если |Δ| ≤ `REPRICE_HITL_THRESHOLD_PCT`
   (10%), иначе `draft` (ждёт подтверждения в UI). `mode` = live/dry_run по тумблеру.
6. Применение: `apply_listing_edit` для approved (в dry_run пишет журнал без
   изменений на Авито; live — реально меняет цену в кабинете). Селекторы кабинета:
   перед включением live — одна ручная проверка.
7. AI-сводка: один батч-вызов по всем созданным правкам за прогон →
   `RepriceSummary{headline, items:[{sku, reason}]}`, пишем в `listing_edits.ai_summary`,
   вызов в `llm_runs` (task=`reprice_summary`, версия `REPRICE_SUMMARY_VERSION=v1`).
8. Задача кладёт итог в Redis `reprice:auto:last` (TTL 7 дней): время, создано,
   применено, ошибки, headline.

## API

- `GET /api/v1/our-listings/auto-reprice` → `{enabled, live, mode_effective,
  next_run_at, last: {...}}`.
- `PATCH /api/v1/our-listings/auto-reprice` → `{enabled?, live?}`; включение
  `live` требует `SELLER_EDIT_MODE=live`, иначе 409 с подсказкой.
- `GET /api/v1/our-listings/{sku}/edits?limit=10` — история правок SKU
  (существующий список правок получает фильтр по sku).
- Существующие `POST /our-listings/edits`, `/{id}/approve|reject|apply|revert`
  остаются — ими пользуется новый UI.

## БД

- Миграция 0015: `ALTER TABLE listing_edits ADD COLUMN ai_summary TEXT NULL`.

## Фронтенд

- `frontend/app/our-listings/page.tsx`: панель «Авто-правки» (тумблер вкл/выкл,
  индикатор dry-run/live, «следующий прогон ~03:00 МСК», последний прогон с
  заголовком AI), кнопка боевого режима с confirm.
- Карточки SKU: рекомендация, последняя правка (статус, было→стало, Δ%,
  `ai_summary`), для `draft` — «Подтвердить/Отклонить», для `applied` — «Откатить»,
  список последних правок. Компонент `edits-panel.tsx` разбирается на части,
  переиспользуемые в карточке.
- Удаляем `frontend/app/edits/page.tsx`, пункт «Правки» из шапки; `/edits`
  редиректит на `/our-listings`.

## Безопасность

- Только активные SKU с привязкой к Авито; не ниже себестоимости; шаг ≤5%;
  HITL >10%; один прогон в сутки; dry-run по умолчанию; live — двойной гейт
  (env + тумблер) и подтверждение в UI; откат доступен для каждой применённой правки.

## План реализации

1. Миграция 0015 + поле модели; конфиг `reprice_auto_cron`, `reprice_auto_enabled`
   (дефолт выкл) и Redis-состояние.
2. AI: схема `RepriceSummary`, промпт, задача `summarize_price_edits`, версия,
   `record_llm_run`.
3. Сервис `app/services/reprice.py`: `AutoRepriceState` (Redis get/set),
   `select_auto_edits(...)` (чистая функция отбора), `make_summary_items(...)`.
4. Worker: actor `auto_reprice` (оркестрация + применение + AI + Redis-итог).
5. Планировщик: cron-джойн `_auto_reprice`.
6. API: auto-reprice GET/PATCH, фильтр `sku` в списке правок.
7. Фронтенд: компонент авто-панели, интеграция правок в карточки SKU, удаление
   страницы и пункта меню, редирект.
8. Тесты: отбор SKU и пороги, состояние тумблера, парсинг AI-сводки, лёгкий
   smoke API. CHANGELOG/доки, релиз v0.29.0, деплой, проверка dry-run на проде.

## Тестирование

- `select_auto_edits`: cost-floor, шаг, HITL, занятые SKU, без avito-ссылки.
- Redis-состояние: дефолт выключено, PATCH live при dry-run env → отказ.
- AI-сводка: парсинг ответа и мэппинг reason по sku (мок клиента).
- Существующие тесты правок не ломаются.
