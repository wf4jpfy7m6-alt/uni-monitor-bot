import asyncio
import logging
import os

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


def _build_prompt(position: dict, network: str) -> str:
    in_range    = position.get("in_range", False)
    token0      = position.get("token0", "?")
    token1      = position.get("token1", "?")
    lower       = position.get("price_lower", 0)
    upper       = position.get("price_upper", 0)
    current     = position.get("current_price", 0)
    value_usd   = position.get("value_usd", 0)
    token_id    = position.get("token_id", "?")

    status_str = "В диапазоне ✅" if in_range else "ВНЕ диапазона ❌"

    if current > 0 and not in_range:
        if current < lower:
            dist_pct = (lower - current) / current * 100
            dist_str = f"Цена ниже нижней границы на {dist_pct:.1f}% (нужен рост +${lower - current:,.0f})"
        else:
            dist_pct = (current - upper) / current * 100
            dist_str = f"Цена выше верхней границы на {dist_pct:.1f}% (нужно снижение -${current - upper:,.0f})"
    elif in_range and upper > lower:
        pos_pct = (current - lower) / (upper - lower) * 100
        dist_str = f"Позиция на {pos_pct:.0f}% от нижней границы диапазона"
    else:
        dist_str = "Нет данных о расстоянии"

    width_pct = (upper - lower) / lower * 100 if lower > 0 else 0

    return f"""Ты DeFi-аналитик. Проанализируй позицию в пуле ликвидности и дай чёткие рекомендации.

ДАННЫЕ ПОЗИЦИИ:
- Сеть: {network}
- NFT ID: {token_id}
- Пара: {token0}/{token1}
- Статус: {status_str}
- Нижняя граница диапазона: ${lower:,.2f}
- Верхняя граница диапазона: ${upper:,.2f}
- Текущая цена: ${current:,.2f}
- Ширина диапазона: {width_pct:.1f}%
- {dist_str}
- Стоимость позиции: ${value_usd:,.2f}

ЗАДАЧА:
Дай анализ в формате (строго придерживайся структуры, пиши кратко):

📌 *Ситуация*
[1-2 предложения — что происходит с позицией]

⚠️ *Риски*
[1-2 конкретных риска для этой позиции]

✅ *Рекомендация*
[Конкретное действие: держать / скорректировать диапазон / вывести ликвидность — с обоснованием]

Пиши на русском языке. Будь конкретным, избегай общих фраз."""


async def analyze_position(position: dict, network: str = "") -> str:
    if not GEMINI_API_KEY:
        return "⚠️ GEMINI\\_API\\_KEY не задан в переменных окружения."

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = _build_prompt(position, network)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text

    except ImportError:
        return await _fallback_generativeai(position, network)

    except Exception as exc:
        logger.error("Gemini (google.genai) error: %s", exc)
        return await _fallback_generativeai(position, network)


async def _fallback_generativeai(position: dict, network: str) -> str:
    """Запасной вариант — старый пакет google.generativeai."""
    try:
        import google.generativeai as genai_old
        genai_old.configure(api_key=GEMINI_API_KEY)
        model = genai_old.GenerativeModel("gemini-1.5-flash")
        prompt = _build_prompt(position, network)
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except Exception as exc:
        logger.error("Gemini fallback error: %s", exc)
        return f"⚠️ Ошибка AI анализа: {exc}"
