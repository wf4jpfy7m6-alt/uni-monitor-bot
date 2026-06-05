import os
import aiohttp
import json
import logging
import inspect

logger = logging.getLogger(__name__)

# Берём ключ Gemini из переменных окружения Railway
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

async def analyze_position(position: dict, network: str = None) -> str:
    """
    Анализ позиции через Gemini 1.5 Flash.
    """
    if not GEMINI_API_KEY:
        return "⚠️ Ошибка: GEMINI_API_KEY не задан в настройках Railway."

    # Очистка данных от корутин (защита от краха)
    clean_pos = {}
    for k, v in position.items():
        if inspect.iscoroutine(v):
            clean_pos[k] = await v
        else:
            clean_pos[k] = v

    # Промпт
    prompt = f"Проанализируй DeFi позицию: {json.dumps(clean_pos, default=str)}. Дай краткие рекомендации на русском языке."

    # Правильный URL для API v1beta
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Ошибка Gemini {resp.status}: {text}")
                    return f"⚠️ Ошибка Gemini (код {resp.status})"
                
                data = await resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return f"⚠️ Критическая ошибка анализа"
