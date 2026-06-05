import os
import aiohttp
import json
import logging
import inspect

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def clean_data(data):
    """Рекурсивная очистка данных от корутин."""
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
        clean_pos = await clean_data(position)
        prompt = f"Проанализируй DeFi позицию: {json.dumps(clean_pos, default=str)}. Дай краткие рекомендации на русском языке."

        # Используем обновленный идентификатор модели
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=20) as resp:
                response_text = await resp.text()
                
                if resp.status != 200:
                    logger.error(f"Gemini API Error {resp.status}: {response_text}")
                    return f"⚠️ Ошибка Gemini (код {resp.status})"
                
                data = json.loads(response_text)
                return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        logger.error(f"Ошибка в ai_analyst: {e}")
        return "⚠️ Ошибка анализа"
