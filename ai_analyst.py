import os
import aiohttp
import json
import logging

logger = logging.getLogger(__name__)

# Берём API-ключ Gemini из переменных окружения Railway
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def analyze_position(position: dict, network: str = None) -> str:
    """
    Отправляет данные позиции в Gemini 1.5 Flash и получает структурированный анализ.
    """
    # Безопасное извлечение статуса диапазона
    in_range = position.get("in_range", False)
    status_text = "В ДИАПАЗОНЕ ✅" if in_range else "ВНЕ ДИАПАЗОНА 🚨"
    
    # Определяем сеть
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

    # Формируем промпт
    prompt = f"""Ты — высококлассный DeFi-аналитик, специализирующийся на Uniswap v3 и Aerodrome Slipstream liquidity positions.
Проанализируй текущую LP-позицию и дай конкретные рекомендации на русском языке.

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

Ответь строго в таком формате (используй Markdown-разметку для Telegram):

📊 *Ситуация:*
[1-2 предложения о текущем положении пула и цены]

🎯 *Варианты действий:*
1️⃣ [Вариант 1 — название]
→ [Описание что конкретно делать]

2️⃣ [Вариант 2 — название]  
→ [Описание что конкретно делать]

3️⃣ [Вариант 3 — название]
→ [Описание что конкретно делать]

💡 *Рекомендация:*
[Что советуешь сделать в первую очередь и почему, 1-2 предложения]

Будь конкретен, используй числа из данных позиции. Не пиши никакого вводного или заключительного текста, только этот шаблон."""

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY не установлен в переменных окружения.")
        return "⚠️ Ошибка ИИ-анализа: на сервере не задан GEMINI_API_KEY в Variables панели Railway."

    # Эндпоинт для работы с моделью Gemini 1.5 Flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 1000
                    }
                }
            ) as resp:
                
                if resp.status != 200:
                    err_body = await resp.text()
                    logger.error(f"Ошибка API Gemini (Статус {resp.status}): {err_body}")
                    return f"⚠️ Gemini API вернул ошибку (Статус {resp.status}). Проверь логи Railway."

                data = await resp.json()
                
                # Парсим стандартную структуру ответа Google Gemini
                try:
                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text_response
                except (KeyError, IndexError) as parse_err:
                    logger.error(f"Неожиданная структура ответа от Gemini: {data}. Ошибка: {parse_err}")
                    return "⚠️ Не удалось разобрать ответ от ИИ-модели. Проверь структуру в логах."

    except Exception as e:
        logger.error(f"Критическая ошибка при вызове Gemini API: {e}")
        return f"⚠️ Ошибка анализа: {str(e)}"
