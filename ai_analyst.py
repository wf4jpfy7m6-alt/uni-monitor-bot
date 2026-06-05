import os
import aiohttp
import json
import logging
import inspect

logger = logging.getLogger(__name__)

# Берём API-ключ Gemini из переменных окружения Railway
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def safe_extract(value):
    """
    Безопасно извлекает значение. Если внутри coroutine (из-за забытого await в bot.py),
    функция автоматически дожидается её выполнения.
    """
    if inspect.iscoroutine(value):
        return await value
    return value

async def analyze_position(position: dict, network: str = None) -> str:
    """
    Отправляет данные позиции в Gemini 1.5 Flash и получает структурированный анализ.
    Защищен от пропуска await в основном файле бота.
    """
    
    # 1. ГЛУБОКАЯ ОЧИСТКА ДАННЫХ (Защита от TypeError coroutine)
    cleaned_position = {}
    for key, val in position.items():
        try:
            cleaned_position[key] = await safe_extract(val)
        except Exception as e:
            logger.warning(f"Не удалось извлечь значение для ключа {key}: {e}")
            cleaned_position[key] = val

    # 2. Безопасное чтение параметров
    in_range = cleaned_position.get("in_range", False)
    status_text = "В ДИАПАЗОНЕ ✅" if in_range else "ВНЕ ДИАПАЗОНА 🚨"
    pos_network = cleaned_position.get("network", network or "Base")
    fee_val = cleaned_position.get("fee", "0.05")

    # Чтение и безопасная конвертация цен в float
    try:
        current_price = float(cleaned_position.get("current_price", 0.0))
        price_lower = float(cleaned_position.get("price_lower", 0.0))
        price_upper = float(cleaned_position.get("price_upper", 0.0))
        value_usd = float(cleaned_position.get("value_usd", 0.0))
    except (ValueError, TypeError):
        current_price = 0.0
        price_lower = 0.0
        price_upper = 0.0
        value_usd = 0.0

    # Определение направления выхода из диапазона
    if current_price < price_lower:
        range_status_detail = "ПОЗИЦИЯ ВЫШЛА ЗА НИЖНЮЮ ГРАНИЦУ (текущая цена ниже диапазона)."
    elif current_price > price_upper:
        range_status_detail = "ПОЗИЦИЯ ВЫШЛА ЗА ВЕРХНЮЮ ГРАНИЦУ (текущая цена выше диапазона)."
    else:
        range_status_detail = "Позиция находится внутри выбранного диапазона и активно генерирует торговые комиссии."

    # 3. Формирование финального промпта
    prompt = f"""Ты — профессиональный DeFi-аналитик, эксперт по Uniswap v3 и Aerodrome Slipstream.
Проанализируй текущую LP-позицию и дай конкретные рекомендации на русском языке.

ДАННЫЕ ПОЗИЦИИ:
- Пара: {cleaned_position.get('token0', 'WETH')}/{cleaned_position.get('token1', 'USDC')}
- Сеть: {pos_network}
- NFT ID: {cleaned_position.get('token_id', 'Неизвестно')}
- Диапазон: ${price_lower:,.2f} — ${price_upper:,.2f}
- Текущая цена: ${current_price:,.2f}
- Комиссия пула: {fee_val}%
- Статус: {status_text}
- Примерная стоимость: ~${value_usd:,.0f}

{range_status_detail}

Ответь строго в таком формате (используй Markdown-разметку для Telegram):

📊 *Ситуация:*
[1-2 sentences about current state based on facts]

🎯 *Варианты действий:*
1️⃣ [Вариант 1]
→ [Что делать]

2️⃣ [Вариант 2]  
→ [Что делать]

3️⃣ [Вариант 3]
→ [Что делать]

💡 *Рекомендация:*
[Итоговый совет, 1-2 предложения]

Пиши только по делу, опираясь на цифры пула. Не выводи никаких приветствий и системных логов."""

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY отсутствует в переменных окружения.")
        return "⚠️ Ошибка ИИ-анализа: на сервере не задан GEMINI_API_KEY в Variables панели Railway."

    # Корректный URL для генерации контента через v1beta
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    # 4. Отправка запроса в Google AI Studio
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 1200
                }
            }
            
            async with session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                if resp.status != 200:
                    err_body = await resp.text()
                    logger.error(f"Ошибка Gemini API (Статус {resp.status}): {err_body}")
                    return f"⚠️ API вернул статус {resp.status}. Проверьте логи сборки в Railway."

                data = await resp.json()
                
                try:
                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    return text_response
                except (KeyError, IndexError) as parse_err:
                    logger.error(f"Ошибка структуры JSON ответа: {data}. Описание: {parse_err}")
                    return "⚠️ Ошибка обработки ответа ИИ. Изменился формат выдачи Google."

    except Exception as e:
        logger.error(f"Критическая ошибка в блоке отправки запроса: {e}")
        return f"⚠️ Сбой модуля ИИ-анализа: {str(e)}"
