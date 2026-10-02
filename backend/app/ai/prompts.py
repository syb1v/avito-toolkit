from collections.abc import Sequence

from app.services.pricing import RepricingContext

PRICE_ADVISOR_VERSION = "v1"
DIGEST_VERSION = "v1"
MODERATION_VERSION = "v1"

PRICE_ADVISOR_SYSTEM_PROMPT = """Ты коммерческий директор и ценовой аналитик на Авито.
Анализируй рыночные метрики и текущую цену товара.
Учитывай себестоимость, скорость вымывания конкурентов и коридор цен.
Отвечай строго в формате JSON по заданной схеме, без пояснений вне JSON.
Если данных недостаточно, выбирай стратегию keep_current и отражай это в рисках."""

DIGEST_SYSTEM_PROMPT = """Ты аналитик рынка Авито. Составь сжатую сводку по поисковой выдаче:
что происходит с ценами, как ведёт себя спрос (скорость вымывания объявлений),
какие действия предпринять продавцу. Опирайся только на переданные метрики.
Отвечай строго в формате JSON по заданной схеме, без пояснений вне JSON."""

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
) -> str:
    top_lines = "\n".join(
        f"- {title} — {price if price is not None else 'цена не указана'} руб."
        for title, price in top_listings
    )
    history_lines = "\n".join(
        f"- {day}: медиана {median_value if median_value is not None else '—'} руб."
        for day, median_value in history
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

Сделай сводку и предложи действия."""


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
