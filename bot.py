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

# ── Переменные окружения и дефолты ───────────────────────────────────────────
DEFAULT_WALLET = os.getenv("WALLET_ADDRESS", "0x1074520dd10d6bad7d760f1762c435f658a8f21a")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))

BTN_STATUS = "📊 Статус позиций"
BTN_ANALYZE = "🔍 AI Анализ"
BTN_ADD = "🟢 Добавить позицию"
BTN_REMOVE = "🔴 Удалить позицию"

# Состояния диалога (States)
CHOOSING_NETWORK, ENTERING_WALLET, ENTERING_GAUGE, CONFIRM_REMOVE = range(4)

position_states = {}

# ── Инициализация Базы Данных SQLite ──────────────────────────────────────────
DB_PATH = "/app/data/positions.db"

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
    # Если база пуста, добавляем ваш дефолтный стартовый конфиг
    cursor.execute("SELECT COUNT(*) FROM positions")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
            ("Base (Aerodrome)", DEFAULT_WALLET, "0x1E012d2A200B9c7e0DDc968Eba14e2E7C332A04A")
        )
        cursor.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
            ("Arbitrum", DEFAULT_WALLET, None)
        )
        conn.commit()
    conn.close()

init_db()

# ── Управление клавиатурой ────────────────────────────────────────────────────
def get_main_keyboard():
    keyboard = [
        [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_ANALYZE)],
        [KeyboardButton(BTN_ADD), KeyboardButton(BTN_REMOVE)]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# ── Сбор данных по всем пулам из БД ───────────────────────────────────────────
async def get_all_positions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT network, wallet_address, gauge_address FROM positions")
    rows = cursor.fetchall()
    conn.close()

    all_positions = []
    
    for network, wallet, gauge in rows:
        if "Arbitrum" in network:
            try:
                # Динамически создаем монитор под конкретный кошелек из базы
                m = PositionMonitor(wallet)
                uni = await m.get_all_positions()
                all_positions.extend(uni)
            except Exception as e:
                logger.error(f"Ошибка Uniswap (Arbitrum) для кошелька {wallet}: {e}")
        elif "Base" in network or "Aerodrome" in network:
            try:
                aero_m = AerodromeMonitor(wallet, gauge)
                aero = await aero_m.get_positions()
                all_positions.extend(aero)
            except Exception as e:
                logger.error(f"Ошибка Aerodrome (Base) для кошелька {wallet}: {e}")
                
    return all_positions

# ── Логика вывода рекомендаций ────────────────────────────────────────────────
def generate_fallback_recommendation(p: dict) -> str:
    cur_p = p.get("current_price", 0.0)
    p_low = p.get("price_lower", 0.0)
    p_up = p.get("price_upper", 0.0)
    val_usd = p.get("value_usd", 0.0)

    if cur_p < p_low:
        direction = "ниже нижней границы"
        action_move = f"Закрыть текущую позицию и открыть новую ниже по тренду (например, с центром у текущей цены ${cur_p:,.0f}), чтобы сразу возобновить получение торговых комиссий."
    else:
        direction = "выше верхней границы"
        action_move = "Ваша позиция полностью ушла в USDC. Можно зафиксировать прибыль, подождать локального отката либо перезайти в более широкий коридор."

    return (
        f"\n🚨 *ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n"
        f"*Ситуация:* Цена ETH (${cur_p:,.2f}) ушла {direction}. "
        f"Позиция на 100% конвертировалась в один актив, комиссии больше НЕ начисляются, капитал простаивает.\n\n"
        f"*Варианты действий:*\n"
        f"1️⃣ *Переместить диапазон вниз (Ребаланс):*\n"
        f"     ↳ {action_move}\n"
        f"2️⃣ *Держать и ждать возврата:* \n"
        f"     ↳ Ничего не делать. Если рынок развернется и цена вернется в коридор (${p_low:,.0f} — ${p_up:,.0f}), позиция автоматически активируется снова.\n"
        f"3️⃣ *Вывести ликвидность:* \n"
        f"     ↳ Полностью забрать средства из пула.\n\n"
        f"💡 *Рекомендация:* Оцените стоимость транзакции (Gas). Если баланс пула (~${val_usd:,.0f}) небольшой, частые ребалансировки съедят доход."
    )

# ── Команды бота ──────────────────────────────────────────────────────────────
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
        await msg.edit_text("😶 Активных LP-позиций в пулах не обнаружено.", reply_markup=get_main_keyboard())
        return

    text = "📊 *Текущий статус твоих позиций:*\n\n"
    text += "═" * 15 + "\n\n"
    
    for p in positions:
        emoji = "✅" if p["in_range"] else "🚨"
        status_label = "В диапазоне" if p["in_range"] else "❗ ВНЕ диапазона"
        cur_p = p.get("current_price", 0.0)
        p_low = p.get("price_lower", 0.0)
        p_up = p.get("price_upper", 0.0)
        val_usd = p.get("value_usd", 0.0)
        
        text += (
            f"{emoji} *{p['token0']}/{p['token1']}* — _{p['network']}_\n"
            f"   NFT #{p['token_id']}\n"
            f"   Коридор: ${p_low:,.0f} — ${p_up:,.0f}\n"
            f"   Текущая цена: ${cur_p:,.2f}\n"
            f"   Статус: *{status_label}*\n"
            f"   Текущая стоимость: ~${val_usd:,.0f}\n"
        )
        if not p["in_range"]:
            text += generate_fallback_recommendation(p)
        text += "\n" + "═" * 15 + "\n\n"

    await msg.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    msg = await update.message.reply_text("🧠 Запускаю AI-аналитика...")
    positions = await get_all_positions()
    
    if not positions:
        await msg.edit_text("😶 Позиций для анализа не найдено.", reply_markup=get_main_keyboard())
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

# ── СЦЕНАРИЙ ДИАЛОГА: ДОБАВЛЕНИЕ ПОЗИЦИИ ──────────────────────────────────────
async def add_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_keyboard = [["Arbitrum", "Base (Aerodrome)"], ["❌ Отмена"]]
    await update.message.reply_text(
        "Вы запускаете мастер добавления новой позиции.\n"
        "Выбирайте целевую сеть пула:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return CHOOSING_NETWORK

async def add_position_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    network = update.message.text
    if network == "❌ Отмена":
        await update.message.reply_text("Добавление отменено.", reply_markup=get_main_keyboard())
        return ConversationHandler.END
    
    context.user_data["new_network"] = network
    await update.message.reply_text(
        f"Сеть: {network}.\nТеперь введите EVM адрес кошелька (0x...), который владеет пулом/NFT:",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True)
    )
    return ENTERING_WALLET

async def add_position_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    if wallet == "❌ Отмена":
        await update.message.reply_text("Добавление отменено.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    if not wallet.startswith("0x") or len(wallet) != 42:
        await update.message.reply_text("⚠️ Неверный формат адреса. Попробуйте еще раз или нажмите '❌ Отмена':")
        return ENTERING_WALLET

    context.user_data["new_wallet"] = wallet

    if "Base" in context.user_data["new_network"]:
        await update.message.reply_text(
            "Для сети Base (Aerodrome) требуется указать адрес Gauge-контракта пула.\n"
            "Введите адрес Gauge контракта (или отправьте 'пропустить', если стейкинг не используется):"
        )
        return ENTERING_GAUGE
    else:
        # Для Arbitrum Gauge не нужен, сохраняем сразу
        return await save_position_to_db(update, context, None)

async def add_position_gauge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gauge_txt = update.message.text.strip()
    if gauge_txt == "❌ Отмена":
        await update.message.reply_text("Добавление отменено.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    gauge = None if gauge_txt.lower() in ["пропустить", "skip"] else gauge_txt
    if gauge and (not gauge.startswith("0x") or len(gauge) != 42):
        await update.message.reply_text("⚠️ Неверный формат адреса Gauge. Попробуйте еще раз или напишите 'пропустить':")
        return ENTERING_GAUGE

    return await save_position_to_db(update, context, gauge)

async def save_position_to_db(update: Update, context: ContextTypes.DEFAULT_TYPE, gauge_address):
    network = context.user_data.get("new_network")
    wallet = context.user_data.get("new_wallet")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?, ?, ?)",
        (network, wallet, gauge_address)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🎉 Позиция успешно добавлена в мониторинг!\n"
        f"Сеть: {network}\nКошелек: {wallet[:6]}...{wallet[-4:]}",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END


# ── СЦЕНАРИЙ ДИАЛОГА: УДАЛЕНИЕ ПОЗИЦИИ ───────────────────────────────────────
async def remove_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, network, wallet_address FROM positions")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("В базе нет зарегистрированных позиций для удаления.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    text = "Выберите номер позиции, которую хотите **УДАЛИТЬ** из мониторинга:\n\n"
    keyboard = []
    for row in rows:
        p_id, net, wall = row
        text += f"🔹 *[{p_id}]* Сеть: {net} | Кошелек: {wall[:6]}...{wall[-4:]}\n"
        keyboard.append([f"Удалить [{p_id}]"])
    
    keyboard.append(["❌ Отмена"])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True))
    return CONFIRM_REMOVE

async def remove_position_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    if msg == "❌ Отмена":
        await update.message.reply_text("Удаление отменено.", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    try:
        # Извлекаем ID из строки формата "Удалить [ID]"
        p_id = int(msg.split("[")[1].split("]")[0])
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM positions WHERE id = ?", (p_id,))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"🛑 Позиция #{p_id} успешно удалена из отслеживания.", reply_markup=get_main_keyboard())
    except Exception as e:
        await update.message.reply_text("⚠️ Ошибка: не удалось распознать выбор. Попробуйте снова.", reply_markup=get_main_keyboard())
    
    return ConversationHandler.END

async def dialog_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие прервано.", reply_markup=get_main_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# ── Текстовый роутер главного меню ───────────────────────────────────────────
async def text_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    if user_text == BTN_STATUS:
        await status_command(update, context)
    elif user_text == BTN_ANALYZE:
        await analyze_command(update, context)

# ── Цикл фонового автомониторинга ─────────────────────────────────────────────
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

                    cur_p = p.get("current_price", 0.0)
                    p_low = p.get("price_lower", 0.0)
                    p_up = p.get("price_upper", 0.0)

                    text = (
                        f"🚨 *ВНИМАНИЕ: ПОЗИЦИЯ ВЫШЛА ИЗ ДИАПАЗОНА!*\n\n"
                        f"*{p['token0']}/{p['token1']}* — _{p['network']}_\n"
                        f"NFT #{p['token_id']}\n"
                        f"Границы пула: ${p_low:,.0f} — ${p_up:,.0f}\n"
                        f"Текущая цена: ${cur_p:,.2f}\n\n"
                        f"{analysis}"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())
                
                elif not was_in_range and p["in_range"]:
                    cur_p = p.get("current_price", 0.0)
                    p_low = p.get("price_lower", 0.0)
                    p_up = p.get("price_upper", 0.0)

                    text = (
                        f"🎉 *ОТЛИЧНЫЕ НОВОСТИ: ПОЗИЦИЯ ВЕРНУЛАСЬ В ДИАПАЗОН!*\n\n"
                        f"✅ *{p['token0']}/{p['token1']}* — _{p['network']}_\n"
                        f"NFT #{p['token_id']}\n"
                        f"Текущая цена ETH: ${cur_p:,.2f}\n"
                        f"Коридор доходности: ${p_low:,.0f} — ${p_up:,.0f}\n\n"
                        f"📈 Капитал снова в работе. Позиция возобновила сбор торговых комиссий в реальном времени!"
                    )
                    if CHAT_ID:
                        await app.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())
                
                position_states[key] = p["in_range"]
        except Exception as e:
            logger.error(f"Критическая ошибка в цикле автомониторинга: {e}")
        await asyncio.sleep(CHECK_INTERVAL)

# ── Запуск приложения ─────────────────────────────────────────────────────────
async def main():
    if not TELEGRAM_TOKEN:
        logger.error("Критическая ошибка: Переменная TELEGRAM_TOKEN не задана!")
        return
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Регистрация пошаговых сценариев (ConversationHandlers)
    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_ADD), add_position_start)],
        states={
            CHOOSING_NETWORK: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_position_network)],
            ENTERING_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_position_wallet)],
            ENTERING_GAUGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_position_gauge)],
        },
        fallbacks=[CommandHandler("cancel", dialog_cancel), MessageHandler(filters.Text("❌ Отмена"), dialog_cancel)],
    )

    remove_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_REMOVE), remove_position_start)],
        states={
            CONFIRM_REMOVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_position_confirm)],
        },
        fallbacks=[CommandHandler("cancel", dialog_cancel), MessageHandler(filters.Text("❌ Отмена"), dialog_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Подключаем диалоги до базового текстового обработчика
    app.add_handler(add_conv)
    app.add_handler(remove_conv)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_menu_handler))

    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        await auto_monitor(app)

if __name__ == "__main__":
    asyncio.run(main())
