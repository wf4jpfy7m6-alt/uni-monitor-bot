import os
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

# Берём API-ключ из переменных окружения Railway
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

async def analyze_position(position: dict, network: str = None) -> str:
    """
    Отправляет данные позиции в Claude и получает структурированный анализ.
    """
    # Безопасное извлечение статуса диапазона
    in_range = position.get("in_range", False)
    status_text = "В ДИАПАЗОНЕ ✅" if in_range else "ВНЕ ДИАПАЗОНА 🚨"
    
    # Определяем сеть: приоритет из словаря, затем из аргумента, иначе дефолт
    pos_network = position.get("network", network or "DeFi")

    # Безопасно достаем комиссию пула (fee)
    fee_val = position.get("fee", "0.05")

    # Извлекаем числовые значения для анализа
    current_price = position.get("current_price", 0.0)
    price_lower = position.get("price_lower", 0.0)
    price_upper = position.get("price_upper", 0.0)

    # Динамический текст в зависимости от выхода за границы диапазона
    if current_price < price_lower:
        range_status_detail = "ПОЗИЦИЯ ВЫШЛА ЗА НИЖНЮЮ ГРАНИЦУ"
    elif current_price > price_upper:
        range_status_detail = "ПОЗИЦИЯ ВЫШЛА ЗА ВЕРХНЮЮ ГРАНИЦУ"
    else:
        range_status_detail = "Позиция активна и зарабатывает комиссии."

    # Формируем четкий промпт для Claude
    prompt = f"""Ты — DeFi-аналитик, специализирующийся на Uniswap v3 и Aerodrome Slipstream liquidity positions.

Проанализируй позицию и дай конкретные рекомендации на русском языке.

ДАННЫЕ ПОЗИЦИИ:
- Пара: {position.get('token0', 'WETH')}/{position.get('token1', 'USDC')}
- Сеть: {pos_network}
- NFT ID: {position.get('token_id', 'Неизвестно')}
- Диапазон: ${price_lower:,.2f} — ${price_upper:,.2f}
- Текущая цена: ${current_price:,.2f}
- Комиссия пула: {fee_val}%
- Статус: {status_text}
- Примерная стоимость: ~${position.get('value_usd', 0.0):,.0f}

{range_status_detail}

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
        return "⚠️ Ошибка ИИ-анализа: на сервере не задан ANTHROPIC_API_KEY в Variables."

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
                    # ИСПРАВЛЕНО: Используем точное официальное имя модели
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 800,
                    "messages": [{"role": "user", "content": prompt}],
                },
            ) as resp:
                
                if resp.status != 200:
                    err_body = await resp.text()
                    logger.error(f"Ошибка API Anthropic (Статус {resp.status}): {err_body}")
                    return f"⚠️ Anthropic API вернул ошибку (Статус {resp.status}). Проверь логи."

                data = await resp.json()
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0]["text"]
                else:
                    logger.error(f"Неожиданная структура ответа API: {data}")
                    return "⚠️ Не удалось получить текст анализа. Проверь логи сервера."

    except Exception as e:
        logger.error(f"Критическая ошибка AI анализа: {e}")
        return f"⚠️ Ошибка анализа: {str(e)}"
