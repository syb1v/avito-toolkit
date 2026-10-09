from collections.abc import Sequence

from app.services.pricing import RepricingContext

PRICE_ADVISOR_VERSION = "v2"
DIGEST_VERSION = "v3"
MODERATION_VERSION = "v2"
DESCRIPTION_REVIEW_VERSION = "v2"
REPRICE_SUMMARY_VERSION = "v2"
SEARCH_FILTERS_VERSION = "v3"
CHAT_PLAN_VERSION = "v1"
CHAT_ANSWER_VERSION = "v1"
FACETS_VERSION = "v1"
AGENT_REPORT_VERSION = "v1"
CONSENSUS_VERSION = "v1"

PRICE_ADVISOR_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты коммерческий директор и ценовой аналитик на Авито.
Анализируй рыночные метрики и текущую цену товара.
Учитывай себестоимость, скорость вымывания конкурентов и коридор цен.
Отвечай строго в формате JSON по заданной схеме, без пояснений вне JSON.
Если данных недостаточно, выбирай стратегию keep_current и отражай это в рисках."""

DIGEST_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты аналитик рынка Авито. Составь сжатую сводку по поисковой выдаче:
что происходит с ценами, как ведёт себя спрос (скорость вымывания объявлений),
какие действия предпринять продавцу. Опирайся только на переданные метрики.
Если передан блок «Наши товары», для товаров, относящихся к этому поиску,
предложи целевую цену в price_suggestions (только реально подходящие по названию;
пустой список допустим). Не выдумывай SKU. Отвечай строго в формате JSON
по заданной схеме, без пояснений вне JSON."""

SEARCH_FILTERS_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты настраиваешь поиски конкурентов на Авито по нашим
товарам. Для каждого товара верни:
- query: короткая поисковая строка (2–5 слов: бренд + модель/линейка), БЕЗ цветов,
  состояния и слов «продам/новый/оригинал»;
- keyword_groups: 1–2 группы, объединённые по AND; в каждой группе — только варианты
  написания ОДНОГО И ТОГО ЖЕ (например [["b&o","bang olufsen"],["beoplay eleven"]]);
  СТРОГО ЗАПРЕЩЕНО добавлять в группы другие модели/линейки (ex, hx, h100, max, pro и т.п.);
- exclude_keywords: слова-исключения, чтобы отсечь лишнее: (а) другие цвета этой модели —
  только те, которых НЕТ в названии товара; (б) другие модели/линейки той же марки;
  (в) мусор: «копия», «реплика», «ремонт», «запчасти», «восстановлен», «неисправен».
Не добавляй в exclude слова, которые уже есть в названии товара.
Отвечай строго JSON по схеме, по одному объекту на товар."""

REPRICE_SUMMARY_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты объясняешь владельцу магазина, почему система
изменила цены его объявлений на Авито. По каждому SKU дай короткое (1–2 предложения)
объяснение на русском: рынок (медиана/P25/P75), позиция цены, стратегия, спрос.
Без выдуманных данных — только переданные метрики. Общий headline — одна строка.
Отвечай строго JSON по схеме."""

DESCRIPTION_REVIEW_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты проверяешь, действительно ли стоп-слово в описании
объявления Авито означает, что товар плохой. Примеры безобидных упоминаний:
«ремонт не требовался», «не б/у», «копия не продаётся», «на запчасти не разбирал»,
«восстановление не делалось». Примеры по делу: «продаю на запчасти», «есть следы ремонта»,
«копия», «неисправен». Для каждого listing_id верни actually_excluded=true, если
стоп-слово по делу и объявление действительно не подходит, иначе false.
reason — коротко на русском. Отвечай строго JSON по схеме."""

MODERATION_SYSTEM_PROMPT = """
Пиши простым человеческим языком: без технических кодов, английских
жаргонизмов и обозначений вроде undercut_p25 — называй вещи словами
(«ниже четверти рынка», «по медиане», «дороже рынка»). Коротко и по делу.
Ты модератор выдачи Авито. Для каждого объявления определи:
- relevant: соответствует ли оно тематике поискового запроса (другая модель,
  аксессуар, запчасть, услуга — это нерелевантно);
- likely_fake_or_copy: признаки подделки, реплики, приманки или обмана
  (аномально низкая цена, "копия/реплика/аналог", продажа на запчасти);
- category: copy (копия/реплика), fake_bait (приманка/обман), irrelevant
  (нерелевант/запчасти/неисправность), duplicate (дубли), none (нормальное);
- confidence: уверенность 0..1;
- reason: краткая причина на русском.
Оценивай по названию, описанию и цене относительно медианы. Отвечай строго JSON по схеме."""


def build_price_prompt(
    *,
    title: str,
    current_price: float,
    cost_price: float | None,
    context: RepricingContext,
) -> str:
    cost_line = (
        f"Себестоимость: {cost_price} руб."
        if cost_price is not None
        else "Себестоимость: не задана"
    )
    return f"""Товар: {title}
Текущая цена: {current_price} руб.
{cost_line}

Метрики рынка (без выбросов):
- Медиана: {context.median} руб.
- 25-й перцентиль: {context.p25} руб.
- 75-й перцентиль: {context.p75} руб.
- Активных конкурентов: {context.active_competitors}
- Снято/продано за 7 дней: {context.delisted_7d}
- Всего активных объявлений: {context.active_total}

Предложи корректировку цены."""


def build_digest_prompt(
    *,
    search_name: str,
    active_count: int,
    new_today: int,
    delisted_today: int,
    delisted_7d: int,
    delisting_velocity: float,
    median: float | None,
    p25: float | None,
    p75: float | None,
    top_listings: Sequence[tuple[str, float | None]],
    history: Sequence[tuple[str, float | None]] = (),
    our_listings: Sequence[tuple[str, str, float | None]] = (),
) -> str:
    top_lines = "\n".join(
        f"- {title} — {price if price is not None else 'цена не указана'} руб."
        for title, price in top_listings
    )
    history_lines = "\n".join(
        f"- {day}: медиана {median_value if median_value is not None else '—'} руб."
        for day, median_value in history
    )
    our_lines = "\n".join(
        f"- SKU {sku}: {title} — наша цена {price if price is not None else '—'} руб."
        for sku, title, price in our_listings
    )
    return f"""Поиск: {search_name}

Активность:
- Активных объявлений: {active_count}
- Новых сегодня: {new_today}
- Снято сегодня: {delisted_today}
- Снято за 7 дней: {delisted_7d}
- Скорость вымывания (снято/активные за 7 дней): {delisting_velocity:.3f}

Цены рынка (после IQR-фильтрации):
- Медиана: {median if median is not None else "—"} руб.
- P25: {p25 if p25 is not None else "—"} руб.
- P75: {p75 if p75 is not None else "—"} руб.

Топ выдачи:
{top_lines or "- нет данных"}

История медианы:
{history_lines or "- нет данных"}

Наши товары (SKU | название | текущая цена):
{our_lines or "- нет данных"}

Сделай сводку и предложи действия. Для подходящих наших товаров дай price_suggestions."""


def build_moderation_prompt(
    *,
    query: str,
    median: float | None,
    items: list[tuple[int, str, float | None, str | None]],
) -> str:
    lines = []
    for item_id, title, price, description in items:
        snippet = (description or "")[:300].replace('"', "'")
        lines.append(
            f'{{"listing_id": {item_id}, "title": {title!r}, "price": {price}, '
            f'"description": {snippet!r}}}'
        )
    return f"""Запрос: {query}
Медиана рынка: {median if median is not None else "—"} руб.

Объявления (JSON):
[{",\n ".join(lines)}]

Верни решение по каждому listing_id, включая категорию."""


def build_description_review_prompt(
    *,
    query: str,
    items: list[tuple[int, str, str, str]],
) -> str:
    lines = []
    for item_id, title, word, snippet in items:
        lines.append(
            f'{{"listing_id": {item_id}, "title": {title!r}, '
            f'"stop_word": {word!r}, "description_snippet": {snippet!r}}}'
        )
    return f"""Поиск: {query}

Объявления со стоп-словом в описании (JSON):
[{",\n ".join(lines)}]

Для каждого listing_id верни actually_excluded и reason."""


def build_reprice_summary_prompt(
    *,
    items: list[tuple[str, str, float, float, str, float | None, float | None, float | None, int]],
) -> str:
    lines = []
    for sku, title, old, new, strategy, median, p25, p75, matched in items:
        lines.append(
            f"- SKU {sku} | {title}\n"
            f"  было {old:.0f} → стало {new:.0f} руб. ({strategy}); "
            f"медиана {median if median is not None else '—'}, "
            f"P25 {p25 if p25 is not None else '—'}, P75 {p75 if p75 is not None else '—'}, "
            f"конкурентов {matched}"
        )
    return (
        "Правки цен за ночной прогон:\n"
        + "\n".join(lines)
        + "\n\nВерни headline и reason по каждому SKU."
    )


def build_search_filters_prompt(
    *,
    items: list[tuple[int | None, str, str | None]],
) -> str:
    lines = []
    for avito_id, title, category in items:
        lines.append(f'{{"avito_id": {avito_id}, "title": {title!r}, "category": {category!r}}}')
    return (
        "Наши товары (JSON):\n["
        + ",\n ".join(lines)
        + "]\n\nВерни query, keyword_groups и exclude_keywords по каждому avito_id."
    )


def build_chat_plan_prompt(
    *,
    text: str,
    history: list[tuple[str, str]],
    tools: str,
    actions: list[str],
) -> str:
    history_text = "\n".join(f"{role}: {content}" for role, content in history[-8:])
    return (
        f"Доступные инструменты данных:\n{tools}\n\n"
        f"Доступные действия (по подтверждению): {', '.join(actions)}\n\n"
        f"История диалога:\n{history_text or '- нет'}\n\n"
        f"Запрос пользователя: {text}\n\n"
        "Верни JSON: tools (что вызвать), search (имя/часть имени поиска при необходимости), "
        "action_type/action_search/action_sku/action_price — если просят действие."
    )


def build_chat_answer_prompt(
    *,
    text: str,
    history: list[tuple[str, str]],
    tool_data: dict,
) -> str:
    import json as _json

    history_text = "\n".join(f"{role}: {content}" for role, content in history[-8:])
    data_text = _json.dumps(tool_data, ensure_ascii=False, default=str)[:6000]
    return (
        f"История диалога:\n{history_text or '- нет'}\n\n"
        f"Данные из системы (JSON):\n{data_text or '{}'}\n\n"
        f"Запрос пользователя: {text}\n\n"
        "Ответь простым языком. Если в данных есть действие — скажи, что оно ждёт подтверждения."
    )


FACETS_SYSTEM_PROMPT = """
Ты размечаешь объявления Авито по бренду, модели и цвету. Для каждого listing_id верни:
- brand — бренд (например «Bang & Olufsen», «Devialet», «Apple», «Insta360»); если бренд
  не очевиден — «Другое»;
- model — модель или линейка, если понятна из заголовка, иначе пустую строку;
- color — цвет, если указан в заголовке, иначе пустую строку.
Пиши простым человеческим языком, без выдумок. Отвечай строго JSON по схеме.
"""


def build_facets_prompt(*, items: list[tuple[int, str]]) -> str:
    lines = [f'{{"listing_id": {listing_id}, "title": {title!r}}}' for listing_id, title in items]
    return (
        "Объявления (JSON):\n["
        + ",\n ".join(lines)
        + "]\n\nВерни brand/model/color по каждому listing_id."
    )


def build_agent_prompt(*, name: str, category: str, criteria: str, data: str) -> str:
    return (
        f"Агент: {name}\nКатегория: {category}\n\n"
        f"Критерии владельца:\n{criteria}\n\n"
        f"Данные системы (JSON):\n{data}\n\n"
        "Верни headline (одна строка), market_view (3–6 предложений простым языком), "
        "price_actions (по нашим товарам: sku, suggestion, confidence) и risks."
    )


def build_consensus_prompt(*, reports: str, our_items: str) -> str:
    return (
        "Отчёты агентов по категориям (JSON):\n"
        + reports
        + "\n\nНаши товары (sku, название, текущая цена):\n"
        + our_items
        + "\n\nСобери единый план по ценам: только для наших SKU, цена числом, "
        "уверенность и короткая причина простым языком. Если рекомендации агентов "
        "противоречат — выбери безопасный вариант. Верни headline и items."
    )
