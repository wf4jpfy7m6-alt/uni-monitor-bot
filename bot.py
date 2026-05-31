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


async def get_all_positions():
    """Получить позиции со всех протоколов."""
    uni_positions = await monitor.get_all_positions()
    aero_positions = await aero_monitor.get_positions()
    return uni_positions + aero_positions

# Хранилище состояния позиций (in-memory)
position_states = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Статус позиций", callback_data="status")],
        [InlineKeyboardButton("🔍 Детальный анализ", callback_data="analyze")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я мониторю твои позиции Uniswap v3 на Arbitrum и Base.\n\n"
        "Команды:\n"
        "/status — текущее состояние позиций\n"
        "/analyze — AI-анализ всех позиций\n"
        "/help — справка",
        reply_markup=reply_markup
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Загружаю позиции...")
    positions = await get_all_positions()

    if not positions:
        await msg.edit_text("😶 Активных позиций не найдено на Arbitrum и Base.")
        return

    text = "📊 *Твои позиции Uniswap v3:*\n\n"
    for p in positions:
        status_emoji = "✅" if p["in_range"] else "🚨"
        text += (
            f"{status_emoji} *{p['token0']}/{p['token1']}* — {p['network']}\n"
            f"   NFT #{p['token_id']}\n"
            f"   Диапазон: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
            f"   Текущая цена: ${p['current_price']:,.2f}\n"
            f"   Статус: {'В диапазоне' if p['in_range'] else '❗ ВНЕ диапазона'}\n"
            f"   Стоимость: ~${p['value_usd']:,.0f}\n\n"
        )

    await msg.edit_text(text, parse_mode="Markdown")


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Поддержка как обычных сообщений, так и callback кнопок
    if update.message:
        chat_id = update.message.chat_id
        msg = await update.message.reply_text("🧠 Анализирую позиции с помощью AI...")
    else:
        chat_id = update.callback_query.message.chat_id
        msg = await update.callback_query.message.reply_text("🧠 Анализирую позиции с помощью AI...")

    positions = await get_all_positions()

    if not positions:
        await msg.edit_text("😶 Активных позиций не найдено.")
        return

    for p in positions:
        analysis = await analyze_position(p)
        status_emoji = "✅" if p["in_range"] else "🚨"
        text = (
            f"{status_emoji} *{p['token0']}/{p['token1']}* — {p['network']}\n"
            f"NFT #{p['token_id']}\n\n"
            f"{analysis}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        )

    await msg.delete()


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Команды бота:*\n\n"
        "/status — показать все позиции\n"
        "/analyze — AI-анализ с рекомендациями\n"
        "/help — эта справка\n\n"
        f"🔄 Автопроверка каждые {CHECK_INTERVAL // 60} минут.\n"
        f"📍 Кошелёк: `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:]}`",
        parse_mode="Markdown"
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "status":
        await status_command(query, context)
    elif query.data == "analyze":
        await analyze_command(query, context)


async def auto_monitor(app):
    """Фоновая задача — проверяет позиции и шлёт уведомления при выходе из диапазона."""
    while True:
        try:
            positions = await get_all_positions()
            for p in positions:
                key = f"{p['network']}_{p['token_id']}"
                was_in_range = position_states.get(key, True)

                if was_in_range and not p["in_range"]:
                    # Позиция только что вышла из диапазона
                    analysis = await analyze_position(p)
                    text = (
                        f"🚨 *ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n\n"
                        f"*{p['token0']}/{p['token1']}* — {p['network']}\n"
                        f"NFT #{p['token_id']}\n"
                        f"Диапазон: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
                        f"Текущая цена: ${p['current_price']:,.2f}\n\n"
                        f"{analysis}"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(
                            chat_id=CHAT_ID,
                            text=text,
                            parse_mode="Markdown"
                        )

                position_states[key] = p["in_range"]

        except Exception as e:
            logger.error(f"Ошибка в auto_monitor: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    async def post_init(application):
        application.create_task(auto_monitor(application))

    app.post_init = post_init

    logger.info("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
