import os
import aiohttp
import json
import logging
import inspect

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def clean_data(data):
    """Рекурсивная очистка данных от корутин перед сериализацией."""
    if inspect.iscoroutine(data):
        return await data
    if isinstance(data, dict):
        return {k: await clean_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [await clean_data(item) for item in data]
    return data

async def analyze_position(position: dict, network: str = None) -> str:
    """Анализ позиции через Gemini 1.5 Flash."""
    if not GEMINI_API_KEY:
        return "⚠️ Ошибка: GEMINI_API_KEY не задан."

    try:
        # Очищаем данные перед формированием промпта
        clean_pos = await clean_data(position)
        
        prompt = f"Проанализируй DeFi позицию: {json.dumps(clean_pos, default=str)}. Дай краткие рекомендации на русском языке."

        # Эндпоинт для Gemini 1.5 Flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                response_text = await resp.text()
                
                if resp.status != 200:
                    logger.error(f"Gemini API Error {resp.status}: {response_text}")
                    return f"⚠️ Ошибка Gemini (код {resp.status})"
                
                data = json.loads(response_text)
                
                # Безопасное извлечение текста
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as e:
                    logger.error(f"Ошибка парсинга ответа: {e} | Ответ: {data}")
                    return "⚠️ Ошибка формата данных от Gemini"

    except Exception as e:
        logger.error(f"Критическая ошибка в ai_analyst: {e}", exc_info=True)
        return f"⚠️ Критическая ошибка анализа"
