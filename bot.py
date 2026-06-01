import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x1074520dd10d6bad7d760f1762c435f658a8f21a")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))

monitor = PositionMonitor(WALLET_ADDRESS)
aero_monitor = AerodromeMonitor(WALLET_ADDRESS)
position_states = {}


async def get_all_positions():
    uni = await monitor.get_all_positions()
    aero = await aero_monitor.get_positions()
    return uni + aero


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Статус позиций", callback_data="status")],
        [InlineKeyboardButton("🔍 Детальный анализ", callback_data="analyze")],
    ]
    await update.message.reply_text(
        "👋 Привет! Я мониторю твои позиции Uniswap v3 на Arbitrum и Base.\n\n"
        "/status — текущее состояние\n"
        "/analyze — AI-анализ\n"
        "/help — справка",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        msg = await update.message.reply_text("⏳ Загружаю позиции...")
    else:
        msg = await update.callback_query.message.reply_text("⏳ Загружаю позиции...")

    positions = await get_all_positions()
    if not positions:
        await msg.edit_text("😶 Активных позиций не найдено.")
        return

    text = "📊 *Твои позиции:*\n\n"
    for p in positions:
        emoji = "✅" if p["in_range"] else "🚨"
        text += (
            f"{emoji} *{p['token0']}/{p['token1']}* — {p['network']}\n"
            f"   NFT #{p['token_id']}\n"
            f"   Диапазон: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
            f"   Цена: ${p['current_price']:,.2f}\n"
            f"   Статус: {'В диапазоне' if p['in_range'] else '❗ ВНЕ диапазона'}\n"
            f"   Стоимость: ~${p['value_usd']:,.0f}\n\n"
        )
    await msg.edit_text(text, parse_mode="Markdown")


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        chat_id = update.message.chat_id
        msg = await update.message.reply_text("🧠 Анализирую с помощью AI...")
    else:
        chat_id = update.callback_query.message.chat_id
        msg = await update.callback_query.message.reply_text("🧠 Анализирую с помощью AI...")

    positions = await get_all_positions()
    if not positions:
        await msg.edit_text("😶 Позиций не найдено.")
        return

    for p in positions:
        analysis = await analyze_position(p)
        emoji = "✅" if p["in_range"] else "🚨"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{emoji} *{p['token0']}/{p['token1']}* — {p['network']}\nNFT #{p['token_id']}\n\n{analysis}",
            parse_mode="Markdown"
        )
    await msg.delete()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"ℹ️ *Команды:*\n\n"
        f"/status — позиции\n"
        f"/analyze — AI-анализ\n"
        f"/help — справка\n\n"
        f"🔄 Автопроверка каждые {CHECK_INTERVAL // 60} мин.",
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    if update.callback_query.data == "status":
        await status_command(update.callback_query, context)
    elif update.callback_query.data == "analyze":
        await analyze_command(update.callback_query, context)


async def auto_monitor(app):
    """Фоновый мониторинг — запускается после старта приложения."""
    await asyncio.sleep(15)  # даём боту запуститься
    logger.info("Автомониторинг запущен")
    while True:
        try:
            positions = await get_all_positions()
            logger.info(f"Проверка: {len(positions)} позиций")
            for p in positions:
                key = f"{p['network']}_{p['token_id']}"
                was_in_range = position_states.get(key, True)
                if was_in_range and not p["in_range"]:
                    analysis = await analyze_position(p)
                    text = (
                        f"🚨 *ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n\n"
                        f"*{p['token0']}/{p['token1']}* — {p['network']}\n"
                        f"NFT #{p['token_id']}\n"
                        f"Диапазон: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
                        f"Цена: ${p['current_price']:,.2f}\n\n{analysis}"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
                position_states[key] = p["in_range"]
        except Exception as e:
            logger.error(f"Ошибка мониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    import time
    time.sleep(5)

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        logger.info("Бот запущен")
        await auto_monitor(app)


if __name__ == "__main__":
    asyncio.run(main())
