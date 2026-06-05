import os
import asyncio
import logging
import sqlite3
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

# --- Переменные окружения и дефолты ---
DEFAULT_WALLET = os.getenv("WALLET_ADDRESS", "0x107452dd303bf76bf1753ca359f656abaf21a")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))

BTN_STATUS = "📊 Статус позиций"
BTN_ANALYZE = "🧠 AI Анализ"
BTN_ADD = "🟢 Добавить позицию"
BTN_REMOVE = "🔴 Удалить позицию"

# Состояния диалога (States)
CHOOSING_NETWORK, ENTERING_WALLET, ENTERING_GAUGE, CONFIRM_REMOVE = range(4)

# --- Инициализация Базы Данных SQLite на постоянном диске ---
DB_PATH = "/app/data/positions.db"

# Гарантированно создаем папку для базы данных при старте скрипта
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
    
    # Если база пустая, добавляем дефолтный стартовый конфиг
    cursor.execute("SELECT COUNT(*) FROM positions")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
            ("Base (Aerodrome)", DEFAULT_WALLET, "0x6f8103d2420005c7c300c914b13d7c32aa44")
        )
        cursor.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
            ("Arbitrum", DEFAULT_WALLET, None)
        )
        conn.commit()
    conn.close()

init_db()

# --- Управление клавиатурой ---
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

# --- Обработчики основных кнопок ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой DeFi AI-Агент для мониторинга LP-позиций Uniswap V3 и Aerodrome.",
        reply_markup=get_main_keyboard()
    )

async def handle_status_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запрашиваю текущий статус пулов, подожди немного...")
    
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас нет добавленных позиций для мониторинга.")
        return

    # Разделяем позиции по сетям
    arbitrum_wallets = [p[1] for p in positions if p[0] == "Arbitrum"]
    base_positions = [p for p in positions if p[0] == "Base (Aerodrome)"]

    # 1. Проверяем Arbitrum
    if arbitrum_wallets:
        monitor = PositionMonitor()
        for wallet in set(arbitrum_wallets):
            await monitor.check_positions(context.bot, update.message.chat_id, wallet_address=wallet, force_send=True)

    # 2. Проверяем Base
    if base_positions:
        aero_monitor = AerodromeMonitor()
        for pos in base_positions:
            wallet, gauge = pos[1], pos[2]
            await aero_monitor.check_positions(context.bot, update.message.chat_id, wallet_address=wallet, gauge_address=gauge, force_send=True)

async def handle_analyze_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ИИ-Аналитик изучает твои позиции и генерирует рекомендации...")
    
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("Нет активных позиций для анализа.")
        return

    arbitrum_wallets = [p[1] for p in positions if p[0] == "Arbitrum"]
    base_positions = [p for p in positions if p[0] == "Base (Aerodrome)"]

    # Сбор данных по Arbitrum
    if arbitrum_wallets:
        monitor = PositionMonitor()
        for wallet in set(arbitrum_wallets):
            active_positions = await monitor.get_all_positions(wallet)
            for pos in active_positions:
                report = analyze_position(pos, "Arbitrum")
                await update.message.reply_text(report)

    # Сбор данных по Base
    if base_positions:
        aero_monitor = AerodromeMonitor()
        for pos in base_positions:
            wallet, gauge = pos[1], pos[2]
            active_positions = await aero_monitor.get_all_positions(wallet, gauge)
            for pos_data in active_positions:
                report = analyze_position(pos_data, "Base (Aerodrome)")
                await update.message.reply_text(report)

# --- Мастер добавления позиции (Add Position Conversation) ---
async def add_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [['Arbitrum', 'Base (Aerodrome)'], ['❌ Отмена']]
    await update.message.reply_text(
        "Вы запускаете мастер добавления новой позиции.\nВыберите целевую сеть пула:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return CHOOSING_NETWORK

async def add_position_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    network = update.message.text
    context.user_data['new_pos_network'] = network
    
    await update.message.reply_text(
        f"Сеть: {network}.\nТеперь введите EVM адрес кошелька (0x...), который владеет пулом/NFT:",
        reply_markup=ReplyKeyboardMarkup([['❌ Отмена']], resize_keyboard=True)
    )
    return ENTERING_WALLET

async def add_position_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    if not wallet.startswith("0x") or len(wallet) < 40:
        await update.message.reply_text("Похоже, это не валидный EVM адрес. Попробуйте еще раз или нажмите Отмена:")
        return ENTERING_WALLET
    
    context.user_data['new_pos_wallet'] = wallet
    network = context.user_data['new_pos_network']
    
    if network == "Base (Aerodrome)":
        await update.message.reply_text(
            "Для пулов Aerodrome требуется адрес контракта Gauge (если позиция застейкана).\n"
            "Введите адрес Gauge (0x...) или отправьте 'none', если пул не застейкан:",
            reply_markup=ReplyKeyboardMarkup([['none'], ['❌ Отмена']], resize_keyboard=True)
        )
        return ENTERING_GAUGE
    else:
        # Для Arbitrum Gauge не нужен, сразу сохраняем
        return await save_position_to_db(update, context, None)

async def add_position_gauge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gauge = update.message.text.strip()
    if gauge.lower() == 'none':
        gauge = None
    elif not gauge.startswith("0x") or len(gauge) < 40:
        await update.message.reply_text("Неверный адрес Gauge. Введите 0x... адрес или 'none':")
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
        
        await update.message.reply_text(
            f"✅ Позиция успешно добавления в мониторинг!\nСЕТЬ: {network}\nКОШЕЛЕК: {wallet}\nGAUGE: {gauge or 'Нет'}",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при сохранении в БД: {e}", reply_markup=get_main_keyboard())
        
    return ConversationHandler.END

# --- Мастер удаления позиции (Remove Position Conversation) ---
async def remove_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас пока нет добавленных позиций.")
        return ConversationHandler.END
        
    reply_keyboard = []
    context.user_data['active_positions_list'] = positions
    
    for idx, pos in enumerate(positions):
        gauge_str = f" | Gauge: {pos[2][:6]}..." if pos[2] else ""
        button_text = f"{idx + 1}. {pos[0]} ({pos[1][:6]}...{pos[1][-4:]}{gauge_str})"
        reply_keyboard.append([button_text])
        
    reply_keyboard.append(['❌ Отмена'])
    
    await update.message.reply_text(
        "Выберите позицию, которую хотите УДАЛИТЬ из мониторинга:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return CONFIRM_REMOVE

async def remove_position_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text[0].isdigit():
        await update.message.reply_text("Неверный выбор. Попробуйте снова или отмените опера
