import os
import logging
import google.generativeai as genai
import inspect

logger = logging.getLogger(__name__)

# Инициализация API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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
    """Анализ позиции через официальный SDK Google."""
    if not GEMINI_API_KEY:
        return "⚠️ Ошибка: GEMINI_API_KEY не задан."

    try:
        clean_pos = await clean_data(position)
        prompt = f"Проанализируй DeFi позицию: {str(clean_pos)}. Дай краткие рекомендации на русском языке."

        # Генерация контента через официальный метод
        response = model.generate_content(prompt)
        
        return response.text

    except Exception as e:
        logger.error(f"Критическая ошибка Gemini SDK: {e}")
        return "⚠️ Ошибка анализа (API недоступно)"
