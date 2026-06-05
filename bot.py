import os
import sqlite3

# --- 1. ПАПКА ДЛЯ RAILWAY VOLUME (ПОСТОЯННЫЙ ДИСК) ---
DB_PATH = "/app/data/positions.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# --- 2. ИМПОРТЫ ---
import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)

from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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

# --- Обработка кнопки "Статус позиций" ---
async def handle_status_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запрашиваю текущий статус пулов, подожди немного...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас нет добавленных позиций для мониторинга.")
        return

    arbitrum_wallets = [p[1] for p in positions if p[0] == "Arbitrum"]
    base_positions = [p for p in positions if p[0] == "Base (Aerodrome)"]

    if arbitrum_wallets:
        monitor = PositionMonitor()
        for wallet in set(arbitrum_wallets):
            try:
                await monitor.check_positions(context.bot, update.message.chat_id, wallet_address=wallet, force_send=True)
            except Exception as e:
                logger.error(f"Ошибка Arbitrum: {e}")
                await update.message.reply_text(f"❌ Ошибка получения данных с Arbitrum: {e}")

    if base_positions:
        for pos in base_positions:
            try:
                # Фикс: Передаем кошелек и gauge сразу в конструктор класса
                aero_monitor = AerodromeMonitor(wallet_address=pos[1], gauge_address=pos[2])
                await aero_monitor.check_positions(context.bot, update.message.chat_id, force_send=True)
            except Exception as e:
                logger.error(f"Ошибка Aerodrome: {e}")
                await update.message.reply_text(f"❌ Ошибка получения данных с Base: {e}")

# --- Обработка кнопки "AI Анализ" ---
async def handle_analyze_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ИИ-Аналитик изучает твои позиции...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("Нет активных позиций для анализа.")
        return

    arbitrum_wallets = [p[1] for p in positions if p[0] == "Arbitrum"]
    base_positions = [p for p in positions if p[0] == "Base (Aerodrome)"]

    if arbitrum_wallets:
        monitor = PositionMonitor()
        for wallet in set(arbitrum_wallets):
            try:
                active_positions = await monitor.get_all_positions(wallet)
                for pos in active_positions:
                    await update.message.reply_text(analyze_position(pos, "Arbitrum"))
            except Exception as e:
                logger.error(f"Ошибка ИИ Arbitrum: {e}")
                await update.message.reply_text(f"❌ Ошибка ИИ-анализа Arbitrum: {e}")

    if base_positions:
        for pos in base_positions:
            try:
                # Фикс: Передаем кошелек и gauge сразу в конструктор класса для ИИ-анализа
                aero_monitor = AerodromeMonitor(wallet_address=pos[1], gauge_address=pos[2])
                active_positions = await aero_monitor.get_all_positions()
                for pos_data in active_positions:
                    await update.message.reply_text(analyze_position(pos_data, "Base (Aerodrome)"))
            except Exception as e:
                logger.error(f"Ошибка ИИ Aerodrome: {e}")
                await update.message.reply_text(f"❌ Ошибка ИИ-анализа Base: {e}")

# --- Добавление позиции ---
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
    if not TELEGRAM_TOKEN: return
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
    application.run_polling()

if __name__ == '__main__':
    main()
