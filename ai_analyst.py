import asyncio
import logging
import os

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Модели в порядке приоритета: (endpoint_version, model_name)
MODELS_TO_TRY = [
    ("v1",     "gemini-1.5-flash"),
    ("v1",     "gemini-1.5-pro"),
    ("v1beta", "gemini-2.0-flash-lite"),
    ("v1beta", "gemini-2.0-flash"),
]

GEMINI_BASE = "https://generativelanguage.googleapis.com"


def _build_prompt(position: dict, network: str) -> str:
    in_range  = position.get("in_range", False)
    token0    = position.get("token0", "?")
    token1    = position.get("token1", "?")
    lower     = position.get("price_lower", 0)
    upper     = position.get("price_upper", 0)
    current   = position.get("current_price", 0)
    value_usd = position.get("value_usd", 0)
    token_id  = position.get("token_id", "?")

    status_str = "В диапазоне ✅" if in_range else "ВНЕ диапазона ❌"

    if current > 0 and not in_range:
        if current < lower:
            dist_pct = (lower - current) / current * 100
            dist_str = f"Цена ниже нижней границы на {dist_pct:.1f}% (нужен рост +${lower - current:,.0f})"
        else:
            dist_pct = (current - upper) / current * 100
            dist_str = f"Цена выше верхней границы на {dist_pct:.1f}% (нужно снижение −${current - upper:,.0f})"
    elif in_range and upper > lower:
        pos_pct = (current - lower) / (upper - lower) * 100
        dist_str = f"Цена на {pos_pct:.0f}% от нижней границы диапазона"
    else:
        dist_str = "Нет данных"

    width_pct = (upper - lower) / lower * 100 if lower > 0 else 0

    return f"""Ты DeFi-аналитик. Проанализируй позицию в пуле ликвидности.

ПОЗИЦИЯ:Э
- Сеть: {network}
- NFT ID: {token_id}
- Пара: {token0}/{token1}
- Статус: {status_str}
- Нижняя граница: ${lower:,.2f}
- Верхняя граница: ${upper:,.2f}
- Текущая цена: ${current:,.2f}
- Ширина диапазона: {width_pct:.1f}%
- {dist_str}
- Стоимость: ${value_usd:,.2f}

Ответь строго в этом формате:

📌 *Ситуация*
[1-2 предложения]

⚠️ *Риски*
[1-2 конкретных риска]

✅ *Рекомендация*
[Конкретное действие с обоснованием]

Пиши на русском, кратко и конкретно."""


async def _call_gemini(api_version: str, model: str, prompt: str) -> str:
    url = f"{GEMINI_BASE}/{api_version}/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 512},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            url,
            json=payload,
            params={"key": GEMINI_API_KEY},
        )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def analyze_position(position: dict, network: str = "") -> str:
    if not GEMINI_API_KEY:
        return "⚠️ GEMINI\\_API\\_KEY не задан."

    prompt = _build_prompt(position, network)

    for api_version, model in MODELS_TO_TRY:
        try:
            text = await _call_gemini(api_version, model, prompt)
            logger.info("Gemini ответил: %s/%s", api_version, model)
            return text
        except Exception as exc:
            logger.warning("Модель %s/%s недоступна: %s", api_version, model, exc)

    logger.warning("Все модели Gemini недоступны — используем встроенный анализ")
    return _builtin_analysis(position, network)


def _builtin_analysis(position: dict, network: str) -> str:
    in_range  = position.get("in_range", False)
    lower     = position.get("price_lower", 0)
    upper     = position.get("price_upper", 0)
    current   = position.get("current_price", 0)
    value_usd = position.get("value_usd", 0)
    token0    = position.get("token0", "?")
    token1    = position.get("token1", "?")
    token_id  = position.get("token_id", "?")

    width_pct = (upper - lower) / lower * 100 if lower > 0 else 0

    if in_range:
        pos_pct = (current - lower) / (upper - lower) * 100 if upper > lower else 50
        situation = f"Позиция активна и генерирует комиссии. Цена находится на {pos_pct:.0f}% от нижней границы диапазона."
        if pos_pct < 20:
            risk = "Цена близко к нижней границе — высок риск выхода вниз при коррекции рынка."
            rec = "Следи за ценой. Если цена приблизится к нижней границе вплотную — рассмотри сдвиг диапазона вниз."
        elif pos_pct > 80:
            risk = "Цена близко к верхней границе — высок риск выхода вверх при росте."
            rec = "Следи за ценой. При сильном росте рассмотри расширение диапазона вверх."
        else:
            risk = "Умеренный риск — цена в середине диапазона, возможен выход в любую сторону при волатильности."
            rec = "Держи позицию. Диапазон сбалансирован, активно собираются комиссии."
    else:
        if current < lower:
            dist_pct = (lower - current) / current * 100
            situation = f"Позиция вне диапазона — цена ниже нижней границы на {dist_pct:.1f}%. Комиссии не начисляются, вся ликвидность конвертирована в {token0}."
            if dist_pct < 5:
                risk = "Цена совсем близко к нижней границе — возможен быстрый вход при небольшом росте ETH."
                rec = "Держи позицию. Высокая вероятность возврата в диапазон без изменений."
            elif dist_pct < 20:
                risk = "Цена заметно ниже диапазона. Если ETH продолжит падение — позиция будет вне диапазона долго."
                rec = f"Оцени перспективы роста ETH. Если бычий тренд — держи. Если нет — рассмотри сдвиг диапазона вниз к текущей цене."
            else:
                risk = f"Цена сильно ниже диапазона ({dist_pct:.0f}%). Потери на impermanent loss растут с каждым днём простоя."
                rec = "Рекомендуется вывести ликвидность и переоткрыть позицию с диапазоном вокруг текущей цены."
        else:
            dist_pct = (current - upper) / current * 100
            situation = f"Позиция вне диапазона — цена выше верхней границы на {dist_pct:.1f}%. Комиссии не начисляются, вся ликвидность конвертирована в {token1}."
            risk = "Упущенные комиссии при росте рынка. При коррекции цена вернётся в диапазон."
            rec = "Держи или расширь диапазон вверх чтобы продолжать собирать комиссии при текущих ценах."

    if width_pct < 10:
        width_note = f"⚠️ Диапазон очень узкий ({width_pct:.1f}%) — высокий риск выхода при любом движении, но высокие комиссии когда в диапазоне."
    elif width_pct > 50:
        width_note = f"ℹ️ Диапазон широкий ({width_pct:.1f}%) — низкий риск выхода, но меньшая концентрация ликвидности и комиссий."
    else:
        width_note = ""

    result = (
        f"📌 *Ситуация*\n{situation}\n\n"
        f"⚠️ *Риски*\n{risk}\n\n"
        f"✅ *Рекомендация*\n{rec}"
    )
    if width_note:
        result += f"\n\n{width_note}"

    return result
