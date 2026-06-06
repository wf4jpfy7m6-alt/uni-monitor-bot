import os
import sqlite3
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

# Импортируем ваши модули
from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- КОНФИГУРАЦИЯ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "/app/data/positions.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

BTN_STATUS = "📊 Статус позиций"
BTN_ANALYZE = "🧠 AI Анализ"
BTN_ADD = "🟢 Добавить позицию"
BTN_REMOVE = "🔴 Удалить позицию"

CHOOSING_NETWORK, ENTERING_WALLET, ENTERING_GAUGE, CONFIRM_REMOVE = range(4)

# --- БАЗА ДАННЫХ ---
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT network, wallet_address, gauge_address FROM positions")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- КОМАНДЫ БОТА ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я твой DeFi AI-Агент.", reply_markup=get_main_keyboard())

async def handle_status_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запрос статуса...")
    positions = await get_all_positions()
    for net, wallet, gauge in positions:
        if net == "Base (Aerodrome)":
            try:
                # ИСПРАВЛЕНО: передаем только адрес кошелька
                aero_monitor = AerodromeMonitor(wallet_address=wallet)
                active_positions = await aero_monitor.get_positions()
                if not active_positions:
                    await update.message.reply_text("🔵 Base: позиций не найдено.")
                    continue
                for p in active_positions:
                    report = (f"🌐 {p.get('network')}\n🆔 NFT: `{p.get('token_id')}`\n"
                              f"💰 Стоимость: ${p.get('value_usd'):,.2f}")
                    await update.message.reply_text(report, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Ошибка Base: {e}")
                await update.message.reply_text(f"❌ Ошибка Base: {e}")

async def handle_analyze_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ИИ-Аналитик в работе...")
    positions = await get_all_positions()
    for net, wallet, gauge in positions:
        if net == "Base (Aerodrome)":
            try:
                # ИСПРАВЛЕНО: передаем только адрес кошелька
                aero_monitor = AerodromeMonitor(wallet_address=wallet)
                active_positions = await aero_monitor.get_positions()
                for p_data in active_positions:
                    analysis = await analyze_position(p_data, "Base (Aerodrome)")
                    await update.message.reply_text(analysis, parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка ИИ: {e}")

# --- ОБРАБОТЧИКИ ДИАЛОГОВ (Add/Remove без изменений) ---
# ... (здесь используйте ваши функции add_position_start, remove_position_start и т.д. из вашего файла)

def main():
    if not TELEGRAM_TOKEN: return
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # ... (здесь добавьте ваши ConversationHandler как в оригинале)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Text([BTN_STATUS]), handle_status_request))
    application.add_handler(MessageHandler(filters.Text([BTN_ANALYZE]), handle_analyze_request))
    
    logger.info("Бот запущен.")
    application.run_polling()

if __name__ == '__main__':
    main()
