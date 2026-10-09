from collections.abc import Sequence

from app.services.pricing import RepricingContext

PRICE_ADVISOR_VERSION = "v1"
DIGEST_VERSION = "v2"
MODERATION_VERSION = "v1"
DESCRIPTION_REVIEW_VERSION = "v1"
REPRICE_SUMMARY_VERSION = "v1"

PRICE_ADVISOR_SYSTEM_PROMPT = """Ты коммерческий директор и ценовой аналитик на Авито.
Анализируй рыночные метрики и текущую цену товара.
Учитывай себестоимость, скорость вымывания конкурентов и коридор цен.
Отвечай строго в формате JSON по заданной схеме, без пояснений вне JSON.
Если данных недостаточно, выбирай стратегию keep_current и отражай это в рисках."""

DIGEST_SYSTEM_PROMPT = """Ты аналитик рынка Авито. Составь сжатую сводку по поисковой выдаче:
что происходит с ценами, как ведёт себя спрос (скорость вымывания объявлений),
какие действия предпринять продавцу. Опирайся только на переданные метрики.
Если передан блок «Наши товары», для товаров, относящихся к этому поиску,
предложи целевую цену в price_suggestions (только реально подходящие по названию;
пустой список допустим). Не выдумывай SKU. Отвечай строго в формате JSON
по заданной схеме, без пояснений вне JSON."""

REPRICE_SUMMARY_SYSTEM_PROMPT = """Ты объясняешь владельцу магазина, почему система
изменила цены его объявлений на Авито. По каждому SKU дай короткое (1–2 предложения)
объяснение на русском: рынок (медиана/P25/P75), позиция цены, стратегия, спрос.
Без выдуманных данных — только переданные метрики. Общий headline — одна строка.
Отвечай строго JSON по схеме."""

DESCRIPTION_REVIEW_SYSTEM_PROMPT = """Ты проверяешь, действительно ли стоп-слово в описании
объявления Авито означает, что товар плохой. Примеры безобидных упоминаний:
«ремонт не требовался», «не б/у», «копия не продаётся», «на запчасти не разбирал»,
«восстановление не делалось». Примеры по делу: «продаю на запчасти», «есть следы ремонта»,
«копия», «неисправен». Для каждого listing_id верни actually_excluded=true, если
стоп-слово по делу и объявление действительно не подходит, иначе false.
reason — коротко на русском. Отвечай строго JSON по схеме."""

MODERATION_SYSTEM_PROMPT = """Ты модератор выдачи Авито. Для каждого объявления определи:
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
