import os
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Сделали network необязательным параметром (по умолчанию None), чтобы не ломать старый код,
# если он где-то вызывается с одним аргументом.
async def analyze_position(position: dict, network: str = None) -> str:
    """Отправляет данные позиции в Claude и получает анализ с рекомендациями."""

    in_range = position.get("in_range", False)
    status_text = "В ДИАПАЗОНЕ ✅" if in_range else "ВНЕ ДИАПАЗОНА 🚨"
    
    # Безопасно берем сеть из словаря позиций, если она там есть
    pos_network = position.get("network", network or "DeFi")

    # Безопасно достаем fee. Если его нет (как в Aerodrome), пишем "0.05" (стандарт для твоего пула)
    fee_val = position.get("fee", "0.05")

    prompt = f"""Ты — DeFi-аналитик, специализирующийся на Uniswap v3 и Aerodrome Slipstream liquidity positions.

Проанализируй позицию и дай конкретные рекомендации на русском языке.

ДАННЫЕ ПОЗИЦИИ:
- Пара: {position.get('token0', 'WETH')}/{position.get('token1', 'USDC')}
- Сеть: {pos_network}
- NFT ID: {position.get('token_id', 'Неизвестно')}
- Диапазон: ${position.get('price_lower', 0):,.} — ${position.get('price_upper', 0):,.}
- Текущая цена: ${position.get('current_price', 0):,.}
- Комиссия пула: {fee_val}%
- Статус: {status_text}
- Примерная стоимость: ~${position.get('value_usd', 0):,.0f}

{"ПОЗИЦИЯ ВЫШЛА ЗА НИЖНЮЮ ГРАНИЦУ" if position.get('current_price', 0) < position.get('price_lower', 0) else "ПОЗИЦИЯ ВЫШЛА ЗА ВЕРХНЮЮ ГРАНИЦУ" if position.get('current_price', 0) > position.get('price_upper', 0) else "Позиция активна и зарабатывает комиссии."}

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

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY не установлен в переменных окружения.")
        return "⚠️ Ошибка ИИ-анализа: на сервере не задан ANTHROPIC_API_KEY."

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
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                
                if resp.status != 200:
                    err_body = await resp.text()
                    logger.error(f"Ошибка API Anthropic (Статус {resp.status}): {err_body}")
                    return f"⚠️ Anthropic API вернул ошибку (Статус {resp.status})."

                data = await resp.json()
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0]["text"]
                else:
                    logger.error(f"Неожиданный ответ API: {data}")
                    return "⚠️ Не удалось получить анализ. Проверь логи сервера."

    except Exception as e:
        logger.error(f"Ошибка AI анализа: {e}")
        return f"⚠️ Ошибка анализа: {str(e)}"
