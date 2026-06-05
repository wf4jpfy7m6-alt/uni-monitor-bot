import os
import sqlite3

# --- 1. ПАПКА ДЛЯ RAILWAY VOLUME (ПОСТОЯННЫЙ ДИСК) ---
DB_PATH = "/app/data/positions.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# --- 2. ИМПОРТЫ ---
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)

# Импортируем твои мониторы и аналитика
from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

BTN_STATUS = "📊 Статус позиций"
BTN_ANALYZE = "🧠 AI Анализ"
BTN_ADD = "🟢 Добавить позицию"
BTN_REMOVE = "🔴 Удалить позицию"

CHOOSING_NETWORK, ENTERING_WALLET, ENTERING_GAUGE, CONFIRM_REMOVE = range(4)

# --- Инициализация Базы Данных ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            network TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            gauge_address TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_main_keyboard():
    keyboard = [
        [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_ANALYZE)],
        [KeyboardButton(BTN_ADD), KeyboardButton(BTN_REMOVE)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

async def get_all_positions():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT network, wallet_address, gauge_address FROM positions")
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"Ошибка чтения БД: {e}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой DeFi AI-Агент для мониторинга LP-позиций.",
        reply_markup=get_main_keyboard()
    )

# --- Вывод статуса пулов ---
async def handle_status_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запрашиваю текущий статус пулов, подожди немного...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас нет добавленных позиций для мониторинга.")
        return

    for pos in positions:
        net, wallet, gauge = pos[0], pos[1], pos[2]
        
        if net == "Arbitrum":
            try:
                monitor = PositionMonitor()
                # Для Arbitrum вызываем его родной метод (предполагаем get_all_positions или аналогичный)
                if hasattr(monitor, 'get_all_positions'):
                    active_positions = await monitor.get_all_positions(wallet)
                elif hasattr(monitor, 'get_positions'):
                    active_positions = await monitor.get_positions(wallet)
                else:
                    active_positions = []

                if not active_positions:
                    await update.message.reply_text(f"📦 *Arbitrum* ({wallet[:6]}...):\nАктивных позиций не найдено.", parse_mode="Markdown")
                    continue
                
                for p_data in active_positions:
                    msg = p_data if isinstance(p_data, str) else f"Позиция Arbitrum: {p_data}"
                    await update.message.reply_text(msg)
            except Exception as e:
                logger.error(f"Ошибка Arbitrum: {e}")
                await update.message.reply_text(f"❌ Ошибка данных Arbitrum ({wallet[:6]}...): {e}")

        elif net == "Base (Aerodrome)":
            try:
                # Инициализируем твой класс с кошельком и gauge
                aero_monitor = AerodromeMonitor(wallet_address=wallet, gauge_address=gauge)
                
                # Точно вызываем существующий асинхронный метод get_positions() из твоего файла
                active_positions = await aero_monitor.get_positions()
                
                if not active_positions:
                    await update.message.reply_text(f"🔵 *Base (Aerodrome)*:\nАктивных позиций не найдено.", parse_mode="Markdown")
                    continue
                
                # Разбираем массив словарей, который возвращает aerodrome_monitor.py
                for p in active_positions:
                    range_status = "✅ В диапазоне" if p.get("in_range") else "❌ Вне диапазона"
                    
                    report_msg = (
                        f"🌐 *Сеть:* {p.get('network')}\n"
                        f"🆔 *NFT ID:* `{p.get('token_id')}`\n"
                        f"💱 *Пара:* {p.get('token0')} / {p.get('token1')}\n"
                        f"📊 *Статус:* {range_status}\n\n"
                        f"📉 *Нижняя граница:* {p.get('price_lower'):,}\n"
                        f"📈 *Верхняя граница:* {p.get('price_upper'):,}\n"
                        f"💰 *Текущая цена:* {p.get('current_price'):,}\n\n"
                        f"💵 *Общая стоимость:* ${p.get('value_usd'):,.2f}"
                    )
                    await update.message.reply_text(report_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Ошибка Aerodrome: {e}")
                await update.message.reply_text(f"❌ Ошибка данных Base ({wallet[:6]}...): {e}")

# --- Обработка кнопки "AI Анализ" ---
async def handle_analyze_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ИИ-Аналитик изучает твои позиции...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("Нет активных позиций для анализа.")
        return

    for pos in positions:
        net, wallet, gauge = pos[0], pos[1], pos[2]
        
        if net == "Arbitrum":
            try:
                monitor = PositionMonitor()
                method = getattr(monitor, 'get_all_positions', getattr(monitor, 'get_positions', None))
                if method:
                    active_positions = await method(wallet) if asyncio.iscoroutinefunction(method) else method(wallet)
                    for p_data in active_positions:
                        await update.message.reply_text(analyze_position(p_data, "Arbitrum"))
            except Exception as e:
                logger.error(f"Ошибка ИИ Arbitrum: {e}")
                await update.message.reply_text(f"❌ Ошибка ИИ-анализа Arbitrum: {e}")

        elif net == "Base (Aerodrome)":
            try:
                aero_monitor = AerodromeMonitor(wallet_address=wallet, gauge_address=gauge)
                active_positions = await aero_monitor.get_positions()
                for p_data in active_positions:
                    await update.message.reply_text(analyze_position(p_data, "Base (Aerodrome)"))
            except Exception as e:
                logger.error(f"Ошибка ИИ Aerodrome: {e}")
                await update.message.reply_text(f"❌ Ошибка ИИ-анализа Base: {e}")

# --- Мастер добавления позиции ---
async def add_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [['Arbitrum', 'Base (Aerodrome)'], ['❌ Отмена']]
    await update.message.reply_text(
        "Вы запускаете мастер добавления новой позиции.\nВыберите сеть:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return CHOOSING_NETWORK

async def add_position_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pos_network'] = update.message.text
    await update.message.reply_text(
        "Теперь введите EVM адрес кошелька (0x...):",
        reply_markup=ReplyKeyboardMarkup([['❌ Отмена']], resize_keyboard=True)
    )
    return ENTERING_WALLET

async def add_position_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    if not wallet.startswith("0x") or len(wallet) < 40:
        await update.message.reply_text("Неверный адрес кошелька. Попробуйте еще раз:")
        return ENTERING_WALLET
    
    context.user_data['new_pos_wallet'] = wallet
    if context.user_data['new_pos_network'] == "Base (Aerodrome)":
        await update.message.reply_text(
            "Введите адрес Gauge (0x...) для Aerodrome или отправьте 'none':",
            reply_markup=ReplyKeyboardMarkup([['none'], ['❌ Отмена']], resize_keyboard=True)
        )
        return ENTERING_GAUGE
    else:
        return await save_position_to_db(update, context, None)

async def add_position_gauge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gauge = update.message.text.strip()
    if gauge.lower() == 'none':
        gauge = None
    elif not gauge.startswith("0x") or len(gauge) < 40:
        await update.message.reply_text("Неверный адрес Gauge. Попробуйте еще раз или 'none':")
        return ENTERING_GAUGE
    return await save_position_to_db(update, context, gauge)

async def save_position_to_db(update: Update, context: ContextTypes.DEFAULT_TYPE, gauge):
    network = context.user_data['new_pos_network']
    wallet = context.user_data['new_pos_wallet']
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
            (network, wallet, gauge)
        )
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Позиция успешно добавлена!", reply_markup=get_main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка записи в БД: {e}", reply_markup=get_main_keyboard())
    return ConversationHandler.END

# --- Удаление позиции ---
async def remove_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас пока нет сохраненных позиций.")
        return ConversationHandler.END
        
    reply_keyboard = []
    context.user_data['active_positions_list'] = positions
    for idx, pos in enumerate(positions):
        gauge_str = f" | Gauge: {pos[2][:6]}..." if pos[2] else ""
        reply_keyboard.append([f"{idx + 1}. {pos[0]} ({pos[1][:6]}...{pos[1][-4:]}{gauge_str})"])
    reply_keyboard.append(['❌ Отмена'])
    
    await update.message.reply_text("Выберите позицию для УДАЛЕНИЯ:", reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return CONFIRM_REMOVE

async def remove_position_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text[0].isdigit():
        return CONFIRM_REMOVE
    idx = int(text.split('.')[0]) - 1
    positions = context.user_data.get('active_positions_list', [])
    
    if 0 <= idx < len(positions):
        t = positions[idx]
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM positions WHERE network=? AND wallet_address=? AND (gauge_address=? OR (gauge_address IS NULL AND ? IS NULL))",
            (t[0], t[1], t[2], t[2])
        )
        conn.commit()
        conn.close()
        await update.message.reply_text("🗑 Удалено успешно.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.", reply_markup=get_main_keyboard())
    return ConversationHandler.END

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == BTN_STATUS:
        await handle_status_request(update, context)
    elif update.message.text == BTN_ANALYZE:
        await handle_analyze_request(update, context)

def main():
    if not TELEGRAM_TOKEN: 
        logger.error("TELEGRAM_TOKEN не найден в переменных окружения!")
        return
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_ADD), add_position_start)],
        states={
            CHOOSING_NETWORK: [MessageHandler(filters.Text(['Arbitrum', 'Base (Aerodrome)']) & ~filters.Text(['❌ Отмена']), add_position_network)],
            ENTERING_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text(['❌ Отмена']), add_position_wallet)],
            ENTERING_GAUGE: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text(['❌ Отмена']), add_position_gauge)]
        },
        fallbacks=[MessageHandler(filters.Text(['❌ Отмена']) | filters.COMMAND, cancel)]
    )

    remove_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_REMOVE), remove_position_start)],
        states={CONFIRM_REMOVE: [MessageHandler(filters.TEXT & ~filters.Text(['❌ Отмена']), remove_position_confirm)]},
        fallbacks=[MessageHandler(filters.Text(['❌ Отмена']) | filters.COMMAND, cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv)
    application.add_handler(remove_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("Бот успешно запущен и слушает команды...")
    application.run_polling()

if __name__ == '__main__':
    main()
