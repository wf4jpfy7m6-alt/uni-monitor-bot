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

    # Превращаем все значения словаря в обычные типы, 
    # чтобы избежать ошибок типа 'coroutine is not JSON serializable'
    clean_pos = {}
    for k, v in position.items():
        if inspect.iscoroutine(v):
            clean_pos[k] = await v
        else:
            clean_pos[k] = v

    prompt = f"Проанализируй DeFi позицию: {clean_pos}. Дай краткие рекомендации."

    # ВОТ СЮДА ВСТАВЛЯЕМ СТРОГО ЭТОТ URL:
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
        return f"⚠️ Критическая ошибка: {str(e)}"
