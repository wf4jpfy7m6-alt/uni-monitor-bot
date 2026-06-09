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
    ConversationHandler,
)

from monitor import PositionMonitor
from aerodrome_monitor import AerodromeMonitor
from ai_analyst import analyze_position

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
CHAT_ID         = os.getenv("CHAT_ID")
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL", "600"))

DB_PATH = "/app/data/positions.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

BTN_STATUS  = "📊 Статус позиций"
BTN_ANALYZE = "🧠 AI Анализ"
BTN_ADD     = "🟢 Добавить позицию"
BTN_REMOVE  = "🔴 Удалить позицию"

CHOOSING_NETWORK, ENTERING_WALLET, ENTERING_GAUGE, CONFIRM_REMOVE = range(4)


# ── База данных ────────────────────────────────────────────────────────────────

def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            network         TEXT NOT NULL,
            wallet_address  TEXT NOT NULL,
            gauge_address   TEXT
        )
    """)
    # Чаты, которым слать уведомления
    c.execute("""
        CREATE TABLE IF NOT EXISTS alert_chats (
            chat_id INTEGER PRIMARY KEY
        )
    """)
    # Последнее известное состояние каждой позиции
    c.execute("""
        CREATE TABLE IF NOT EXISTS alert_states (
            token_id    TEXT NOT NULL,
            network     TEXT NOT NULL,
            in_range    INTEGER NOT NULL,
            PRIMARY KEY (token_id, network)
        )
    """)
    conn.commit()
    conn.close()


init_db()


def _db_connect():
    return sqlite3.connect(DB_PATH)


async def get_all_positions() -> list:
    try:
        conn = _db_connect()
        rows = conn.execute(
            "SELECT network, wallet_address, gauge_address FROM positions"
        ).fetchall()
        conn.close()
        return rows
    except Exception as exc:
        logger.error("Ошибка чтения позиций: %s", exc)
        return []


def register_chat(chat_id: int) -> None:
    try:
        conn = _db_connect()
        conn.execute(
            "INSERT OR IGNORE INTO alert_chats (chat_id) VALUES (?)", (chat_id,)
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error("Ошибка сохранения chat_id: %s", exc)


def get_alert_chats() -> list[int]:
    try:
        conn = _db_connect()
        rows = conn.execute("SELECT chat_id FROM alert_chats").fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as exc:
        logger.error("Ошибка чтения чатов: %s", exc)
        return []


def get_stored_state(token_id: str, network: str) -> bool | None:
    """Возвращает сохранённый in_range или None если ещё не видели эту позицию."""
    conn = _db_connect()
    row = conn.execute(
        "SELECT in_range FROM alert_states WHERE token_id=? AND network=?",
        (str(token_id), network),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return bool(row[0])


def save_state(token_id: str, network: str, in_range: bool) -> None:
    conn = _db_connect()
    conn.execute(
        "INSERT OR REPLACE INTO alert_states (token_id, network, in_range) VALUES (?,?,?)",
        (str(token_id), network, int(in_range)),
    )
    conn.commit()
    conn.close()


# ── Клавиатура ────────────────────────────────────────────────────────────────

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_STATUS), KeyboardButton(BTN_ANALYZE)],
            [KeyboardButton(BTN_ADD),    KeyboardButton(BTN_REMOVE)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ── Форматирование сообщения о позиции ────────────────────────────────────────

def format_position(p: dict) -> str:
    in_range = p.get("in_range", False)
    current  = p.get("current_price", 0)
    lower    = p.get("price_lower", 0)
    upper    = p.get("price_upper", 0)

    status = "✅ В диапазоне" if in_range else "❌ Вне диапазона"

    # Расстояние до диапазона / позиция внутри
    extra = ""
    if current > 0:
        if not in_range:
            if current < lower:
                diff     = lower - current
                diff_pct = diff / current * 100
                extra = f"📏 *До входа:* +${diff:,.0f} ({diff_pct:.1f}% вверх)\n"
            else:
                diff     = current - upper
                diff_pct = diff / current * 100
                extra = f"📏 *До входа:* −${diff:,.0f} ({diff_pct:.1f}% вниз)\n"
        else:
            if upper > lower:
                pos_pct = (current - lower) / (upper - lower) * 100
                bar = _range_bar(pos_pct)
                extra = f"📍 *В диапазоне:* {bar} {pos_pct:.0f}%\n"

    # Ширина диапазона
    width_str = ""
    if lower > 0 and upper > lower:
        width_pct = (upper - lower) / lower * 100
        width_str = f"📐 *Ширина диапазона:* {width_pct:.1f}%\n"

    return (
        f"🌐 *Сеть:* {p.get('network')}\n"
        f"🆔 *NFT ID:* `{p.get('token_id')}`\n"
        f"💱 *Пара:* {p.get('token0')} / {p.get('token1')}\n"
        f"📊 *Статус:* {status}\n\n"
        f"📉 *Нижняя граница:* {lower:,}\n"
        f"📈 *Верхняя граница:* {upper:,}\n"
        f"💰 *Текущая цена:* {current:,}\n"
        f"{extra}"
        f"{width_str}"
        f"\n💵 *Общая стоимость:* ${p.get('value_usd', 0):,.2f}"
    )


def _range_bar(pct: float, steps: int = 10) -> str:
    """Текстовый прогресс-бар позиции внутри диапазона."""
    filled = round(pct / 100 * steps)
    filled = max(0, min(steps, filled))
    return "▓" * filled + "░" * (steps - filled)


# ── Получение позиций по сети ──────────────────────────────────────────────────

async def fetch_positions_for(net: str, wallet: str) -> list[dict]:
    if net == "Arbitrum":
        monitor = PositionMonitor(wallet_address=wallet)
        method = getattr(
            monitor, "get_all_positions",
            getattr(monitor, "get_positions", None),
        )
        if method:
            return await method() if asyncio.iscoroutinefunction(method) else method()
    elif net == "Base (Aerodrome)":
        return await AerodromeMonitor(wallet_address=wallet).get_positions()
    return []


# ── Фоновая проверка и уведомления ────────────────────────────────────────────

async def check_and_alert(context) -> None:
    """Периодически проверяет позиции и шлёт уведомление при смене статуса."""
    positions = await get_all_positions()
    if not positions:
        return

    chats = get_alert_chats()
    # Добавляем CHAT_ID из env, если задан и ещё не в списке
    if CHAT_ID:
        try:
            env_id = int(CHAT_ID)
            if env_id not in chats:
                chats.append(env_id)
        except ValueError:
            pass

    if not chats:
        logger.info("Нет чатов для уведомлений — пропускаем проверку")
        return

    for net, wallet, _ in positions:
        try:
            active = await fetch_positions_for(net, wallet)
        except Exception as exc:
            logger.error("Ошибка проверки %s %s: %s", net, wallet[:8], exc)
            continue

        for p in active:
            token_id = str(p.get("token_id"))
            network  = p.get("network")
            in_range = p.get("in_range", False)

            prev = get_stored_state(token_id, network)
            save_state(token_id, network, in_range)

            # Уведомляем только при изменении статуса (или при первом обнаружении вне диапазона)
            if prev == in_range:
                continue
            if prev is None and in_range:
                # Первый раз видим — в диапазоне, молчим
                continue

            if in_range:
                header = "✅ Позиция вернулась в диапазон!"
            else:
                header = "🚨 Позиция вышла из диапазона!"

            text = f"{header}\n\n{format_position(p)}"
            for chat_id in chats:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception as exc:
                    logger.error("Ошибка отправки в чат %s: %s", chat_id, exc)


# ── Команды и кнопки ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_chat(update.effective_chat.id)
    await update.message.reply_text(
        "Привет! Я твой DeFi AI-Агент для мониторинга LP-позиций.\n"
        f"🔔 Буду уведомлять тебя при изменении статуса позиций (каждые {CHECK_INTERVAL // 60} мин).",
        reply_markup=get_main_keyboard(),
    )


async def handle_status_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Запрашиваю текущий статус пулов, подожди немного...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас нет добавленных позиций для мониторинга.")
        return

    for net, wallet, _ in positions:
        try:
            active = await fetch_positions_for(net, wallet)
            if not active:
                await update.message.reply_text(
                    f"📦 *{net}* ({wallet[:6]}...):\nАктивных позиций не найдено.",
                    parse_mode="Markdown",
                )
                continue
            for p in active:
                await update.message.reply_text(format_position(p), parse_mode="Markdown")
        except Exception as exc:
            logger.error("Ошибка статуса %s: %s", net, exc)
            await update.message.reply_text(f"❌ Ошибка данных {net} ({wallet[:6]}...): {exc}")


async def handle_analyze_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 ИИ-Аналитик изучает твои позиции...")
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("Нет активных позиций для анализа.")
        return

    for net, wallet, _ in positions:
        try:
            active = await fetch_positions_for(net, wallet)
            for p in active:
                result = await analyze_position(p, net)
                await update.message.reply_text(result, parse_mode="Markdown")
        except Exception as exc:
            logger.error("Ошибка ИИ %s: %s", net, exc)
            await update.message.reply_text(f"❌ Ошибка ИИ-анализа {net}: {exc}")


# ── Мастер добавления позиции ─────────────────────────────────────────────────

async def add_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вы запускаете мастер добавления новой позиции.\nВыберите сеть:",
        reply_markup=ReplyKeyboardMarkup(
            [["Arbitrum", "Base (Aerodrome)"], ["❌ Отмена"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )
    return CHOOSING_NETWORK


async def add_position_network(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_pos_network"] = update.message.text
    await update.message.reply_text(
        "Теперь введите EVM адрес кошелька (0x...):",
        reply_markup=ReplyKeyboardMarkup([["❌ Отмена"]], resize_keyboard=True),
    )
    return ENTERING_WALLET


async def add_position_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet = update.message.text.strip()
    if not wallet.startswith("0x") or len(wallet) < 40:
        await update.message.reply_text("Неверный адрес кошелька. Попробуйте ещё раз:")
        return ENTERING_WALLET

    context.user_data["new_pos_wallet"] = wallet
    if context.user_data["new_pos_network"] == "Base (Aerodrome)":
        await update.message.reply_text(
            "Введите адрес Gauge (0x...) для Aerodrome или отправьте 'none':",
            reply_markup=ReplyKeyboardMarkup([["none"], ["❌ Отмена"]], resize_keyboard=True),
        )
        return ENTERING_GAUGE
    return await save_position_to_db(update, context, None)


async def add_position_gauge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gauge = update.message.text.strip()
    if gauge.lower() == "none":
        gauge = None
    elif not gauge.startswith("0x") or len(gauge) < 40:
        await update.message.reply_text("Неверный адрес Gauge. Попробуйте ещё раз или 'none':")
        return ENTERING_GAUGE
    return await save_position_to_db(update, context, gauge)


async def save_position_to_db(update: Update, context: ContextTypes.DEFAULT_TYPE, gauge):
    network = context.user_data["new_pos_network"]
    wallet  = context.user_data["new_pos_wallet"]
    try:
        conn = _db_connect()
        conn.execute(
            "INSERT INTO positions (network, wallet_address, gauge_address) VALUES (?,?,?)",
            (network, wallet, gauge),
        )
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Позиция успешно добавлена!", reply_markup=get_main_keyboard())
    except Exception as exc:
        await update.message.reply_text(f"❌ Ошибка записи в БД: {exc}", reply_markup=get_main_keyboard())
    return ConversationHandler.END


# ── Удаление позиции ──────────────────────────────────────────────────────────

async def remove_position_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    positions = await get_all_positions()
    if not positions:
        await update.message.reply_text("У вас пока нет сохранённых позиций.")
        return ConversationHandler.END

    context.user_data["active_positions_list"] = positions
    keyboard = []
    for idx, pos in enumerate(positions):
        gauge_str = f" | Gauge: {pos[2][:6]}..." if pos[2] else ""
        keyboard.append([f"{idx + 1}. {pos[0]} ({pos[1][:6]}...{pos[1][-4:]}{gauge_str})"])
    keyboard.append(["❌ Отмена"])

    await update.message.reply_text(
        "Выберите позицию для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )
    return CONFIRM_REMOVE


async def remove_position_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text or not text[0].isdigit():
        return CONFIRM_REMOVE
    idx = int(text.split(".")[0]) - 1
    positions = context.user_data.get("active_positions_list", [])

    if 0 <= idx < len(positions):
        t = positions[idx]
        conn = _db_connect()
        conn.execute(
            "DELETE FROM positions WHERE network=? AND wallet_address=? "
            "AND (gauge_address=? OR (gauge_address IS NULL AND ? IS NULL))",
            (t[0], t[1], t[2], t[2]),
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


# ── Запуск ────────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не найден в переменных окружения!")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()

    add_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_ADD), add_position_start)],
        states={
            CHOOSING_NETWORK: [
                MessageHandler(
                    filters.Text(["Arbitrum", "Base (Aerodrome)"]) & ~filters.Text(["❌ Отмена"]),
                    add_position_network,
                )
            ],
            ENTERING_WALLET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text(["❌ Отмена"]), add_position_wallet)
            ],
            ENTERING_GAUGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Text(["❌ Отмена"]), add_position_gauge)
            ],
        },
        fallbacks=[MessageHandler(filters.Text(["❌ Отмена"]) | filters.COMMAND, cancel)],
    )

    remove_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Text(BTN_REMOVE), remove_position_start)],
        states={
            CONFIRM_REMOVE: [
                MessageHandler(filters.TEXT & ~filters.Text(["❌ Отмена"]), remove_position_confirm)
            ]
        },
        fallbacks=[MessageHandler(filters.Text(["❌ Отмена"]) | filters.COMMAND, cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(add_conv)
    application.add_handler(remove_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    # Фоновая проверка позиций
    application.job_queue.run_repeating(
        check_and_alert,
        interval=CHECK_INTERVAL,
        first=60,  # первая проверка через минуту после старта
    )

    logger.info("Бот запущен. Проверка позиций каждые %d сек.", CHECK_INTERVAL)
    application.run_polling()


if __name__ == "__main__":
    main()
