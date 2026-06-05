import os
import google.generativeai as genai
import inspect
import logging

logger = logging.getLogger(__name__)

# Инициализация API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# Устанавливаем именно то имя модели, которое требует API для вашего проекта
MODEL_NAME = "gemini-3.1-flash-lite"

async def clean_data(data):
    """Рекурсивная очистка данных от корутин перед отправкой в ИИ."""
    if inspect.iscoroutine(data):
        return await data
    if isinstance(data, dict):
        return {k: await clean_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [await clean_data(item) for item in data]
    return data

async def analyze_position(position: dict, network: str = None) -> str:
    """Анализ позиции через Gemini 3.1 Flash-Lite."""
    if not GEMINI_API_KEY:
        return "⚠️ Ошибка: GEMINI_API_KEY не задан в настройках Railway."

    try:
        # Инициализируем модель по техническому идентификатору
        model = genai.GenerativeModel(MODEL_NAME)
        
        clean_pos = await clean_data(position)
        prompt = f"Проанализируй DeFi позицию: {str(clean_pos)}. Дай краткие рекомендации на русском языке."

        # Отправляем запрос
        response = model.generate_content(prompt)
        
        return response.text

    except Exception as e:
        logger.error(f"Ошибка Gemini (модель {MODEL_NAME}): {e}")
        return f"⚠️ Ошибка анализа: проверьте модель в коде."
