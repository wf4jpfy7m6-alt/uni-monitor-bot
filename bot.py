import os
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x1074520dd10d6bad7d760f1762c435f658a8f21a")
GAUGE_ADDRESS = "0x1E012d2A200B9c7e0DDc968Eba14e2E7C332A04A"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))

BTN_STATUS = "📊 Статус позиций"
BTN_ANALYZE = "🔍 AI Анализ"
BTN_ADD = "🟢 Добавить позицию"
BTN_REMOVE = "🔴 Удалить позицию"

monitor = PositionMonitor(WALLET_ADDRESS)
aero_monitor = AerodromeMonitor(WALLET_ADDRESS, GAUGE_ADDRESS)
position_states = {}

def get_main_keyboard():
    keyboard = [
        [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_ANALYZE)],
        [KeyboardButton(BTN_ADD), KeyboardButton(BTN_REMOVE)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def get_all_positions():
    try:
        uni = await monitor.get_all_positions()
    except Exception as e:
        logger.error(f"Ошибка получения позиций Uniswap (Arbitrum): {e}")
        uni = []
    try:
        aero = await aero_monitor.get_positions()
    except Exception as e:
        logger.error(f"Ошибка получения позиций Aerodrome (Base): {e}")
        aero = []
    return uni + aero

def generate_fallback_recommendation(p: dict) -> str:
    if p["current_price"] < p["price_lower"]:
        direction = "ниже нижней границы"
        action_move = f"Закрыть текущую позицию и открыть новую ниже по тренду (например, с центром у текущей цены ${p['current_price']:,.0f}), чтобы сразу возобновить получение торговых комиссий."
    else:
        direction = "выше верхней границы"
        action_move = f"Ваша позиция полностью ушла в USDC. Можно зафиксировать прибыль, подождать локального отката либо перезайти в более широкий коридор."

    return (
        f"\n🚨 *ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n"
        f"*Ситуация:* Цена ETH (${p['current_price']:,.2f}) ушла {direction}. "
        f"Позиция на 100% конвертировалась в один актив, комиссии больше НЕ начисляются, капитал простаивает.\n\n"
        f"*Варианты действий:*\n"
        f"1️⃣ *Переместить диапазон вниз (Ребаланс):*\n"
        f"    ↳ {action_move}\n"
        f"2️⃣ *Держать и ждать возврата:* \n"
        f"    ↳ Ничего не делать. Если рынок развернется и цена вернется в коридор (${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}), позиция автоматически активируется снова. Риск: неопределенное время без доходности.\n"
        f"3️⃣ *Вывести ликвидность:* \n"
        f"    ↳ Полностью забрать средства из пула, чтобы переждать высокую волатильность.\n\n"
        f"💡 *Рекомендация:* Оцените стоимость транзакции (Gas) на Arbitrum/Base. Если текущий баланс позиции (~${p['value_usd']:,.0f}) небольшой, частые ребалансировки могут съесть доход от комиссий. При затяжном падении безопаснее использовать Вариант 1 частями."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я автоматический DeFi-агент. Мониторю твои LP-позиции WETH/USDC на Arbitrum и Base.\n\n"
        "📈 *Используй постоянные кнопки внизу экрана или команды:*\n"
        "/status — Быстрый срез позиций + варианты действий\n"
        "/analyze — Глубокий разбор позиций нейросетью\n"
        "/help — Техническая справка",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Опрашиваю смарт-контракты и собираю метрики...")
    positions = await get_all_positions()
    
    if not positions:
        await msg.edit_text("😶 Активных LP-позиций в пулах не обнаружено.")
        return

    text = "📊 *Текущий статус твоих позиций:*\n\n"
    text += "═" * 15 + "\n\n"
    
    for p in positions:
        emoji = "✅" if p["in_range"] else "🚨"
        status_label = "В диапазоне" if p["in_range"] else "❗ ВНЕ диапазона"
        
        text += (
            f"{emoji} *{p['token0']}/{p['token1']}* — _{p['network']}_\n"
            f"   NFT #{p['token_id']}\n"
            f"   Коридор: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
            f"   Текущая цена: ${p['current_price']:,.2f}\n"
            f"   Статус: *{status_label}*\n"
            f"   Текущая стоимость: ~${p['value_usd']:,.0f}\n"
        )
        if not p["in_range"]:
            text += generate_fallback_recommendation(p)
        text += "\n" + "═" * 15 + "\n\n"

    await msg.edit_text(text, parse_mode="Markdown")

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    msg = await update.message.reply_text("🧠 Запускаю AI-аналитика (OpenAI)...")
    positions = await get_all_positions()
    
    if not positions:
        await msg.edit_text("😶 Позиций для анализа не найдено.")
        return

    for p in positions:
        try:
            analysis = await analyze_position(p)
        except Exception as e:
            logger.error(f"Ошибка работы AI аналитика: {e}")
            analysis = "⚠️ Не удалось получить ответ от ИИ-модели. Воспользуйтесь рекомендациями из /status."

        emoji = "✅" if p["in_range"] else "🚨"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{emoji} *{p['token0']}/{p['token1']}* — *{p['network']}*\nNFT #{p['token_id']}\n\n{analysis}",
            parse_mode="Markdown"
        )
    await msg.delete()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"ℹ️ *Справка по управлению ботом:*\n\n"
        f"Используй нативное меню внизу экрана или стандартные команды:\n"
        f"/status — Вывод балансов, стоимости пулов и флагов активности.\n"
        f"/analyze — Анализ рыночного контекста вокруг пула через ИИ.\n"
        f"/help — Данное меню.\n\n"
        f"🔄 *Фоновый мониторинг:* Активен.\n"
        f"Автопроверка пулов выполняется каждые {CHECK_INTERVAL // 60} минут.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if user_text == BTN_STATUS:
        await status_command(update, context)
    elif user_text == BTN_ANALYZE:
        await analyze_command(update, context)
    elif user_text in [BTN_ADD, BTN_REMOVE]:
        await update.message.reply_text("🛠️ Этот функционал находится в разработке.")

async def auto_monitor(app):
    await asyncio.sleep(10)
    logger.info("Фоновый автомониторинг пулов запущен успешно.")
    while True:
        try:
            positions = await get_all_positions()
            for p in positions:
                key = f"{p['network']}_{p['token_id']}"
                was_in_range = position_states.get(key, True)
                
                if was_in_range and not p["in_range"]:
                    try:
                        analysis = await analyze_position(p)
                    except Exception:
                        analysis = generate_fallback_recommendation(p)

                    text = (
                        f"🚨 *ВНИМАНИЕ: ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n\n"
                        f"*{p['token0']}/{p['token1']}* — _{p['network']}_\n"
                        f"NFT #{p['token_id']}\n"
                        f"Границы пула: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n"
                        f"Текущая цена: ${p['current_price']:,.2f}\n\n"
                        f"{analysis}"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())
                
                elif not was_in_range and p["in_range"]:
                    text = (
                        f"🎉 *ОТЛИЧНЫЕ НОВОСТИ: ПОЗИЦИЯ ВЕРНУЛАСЬ В ДИАПАЗОН!*\n\n"
                        f"✅ *{p['token0']}/{p['token1']}* — _{p['network']}_\n"
                        f"NFT #{p['token_id']}\n"
                        f"Текущая цена ETH: ${p['current_price']:,.2f}\n"
                        f"Коридор доходности: ${p['price_lower']:,.0f} — ${p['price_upper']:,.0f}\n\n"
                        f"📈 Капитал снова в работе. Позиция возобновила сбор торговых комиссий в реальном времени!"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())
                
                position_states[key] = p["in_range"]
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле автомониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    if not TELEGRAM_TOKEN:
        logger.error("Критическая ошибка: Переменная TELEGRAM_TOKEN не задана!")
        return
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_menu_handler))

    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        await auto_monitor(app)

if __name__ == "__main__":
    asyncio.run(main())
