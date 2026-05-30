import os
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


async def analyze_position(position: dict) -> str:
    """Отправляет данные позиции в Claude и получает анализ с рекомендациями."""

    in_range = position["in_range"]
    status_text = "В ДИАПАЗОНЕ ✅" if in_range else "ВНЕ ДИАПАЗОНА 🚨"

    prompt = f"""Ты — DeFi-аналитик, специализирующийся на Uniswap v3 liquidity positions.

Проанализируй позицию и дай конкретные рекомендации на русском языке.

ДАННЫЕ ПОЗИЦИИ:
- Пара: {position['token0']}/{position['token1']}
- Сеть: {position['network']}
- NFT ID: {position['token_id']}
- Диапазон: ${position['price_lower']:,.2f} — ${position['price_upper']:,.2f}
- Текущая цена: ${position['current_price']:,.2f}
- Комиссия пула: {position['fee']}%
- Статус: {status_text}
- Примерная стоимость: ~${position['value_usd']:,.0f}

{"ПОЗИЦИЯ ВЫШЛА ЗА НИЖНЮЮ ГРАНИЦУ" if position['current_price'] < position['price_lower'] else "ПОЗИЦИЯ ВЫШЛА ЗА ВЕРХНЮЮ ГРАНИЦУ" if position['current_price'] > position['price_upper'] else "Позиция активна и зарабатывает комиссии."}

Дай ответ строго в таком формате:

📊 *Ситуация:*
[1-2 предложения о текущем положении]

🎯 *Варианты действий:*
1️⃣ [Вариант 1 — название]
→ [Описание что делать]

2️⃣ [Вариант 2 — название]  
→ [Описание что делать]

3️⃣ [Вариант 3 — название]
→ [Описание что делать]

💡 *Рекомендация:*
[Что советуешь и почему, 1-2 предложения]

Будь конкретен, используй числа из данных позиции. Не пиши лишнего."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                data = await resp.json()
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0]["text"]
                else:
                    logger.error(f"Неожиданный ответ API: {data}")
                    return "⚠️ Не удалось получить анализ. Проверь API ключ."

    except Exception as e:
        logger.error(f"Ошибка AI анализа: {e}")
        return f"⚠️ Ошибка анализа: {str(e)}"
