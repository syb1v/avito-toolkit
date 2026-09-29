from app.services.pricing import RepricingContext

PRICE_ADVISOR_VERSION = "v1"

PRICE_ADVISOR_SYSTEM_PROMPT = """Ты коммерческий директор и ценовой аналитик на Авито.
Анализируй рыночные метрики и текущую цену товара.
Учитывай себестоимость, скорость вымывания конкурентов и коридор цен.
Отвечай строго в формате JSON по заданной схеме, без пояснений вне JSON.
Если данных недостаточно, выбирай стратегию keep_current и отражай это в рисках."""


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
        else ("Себестоимость: не задана")
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
