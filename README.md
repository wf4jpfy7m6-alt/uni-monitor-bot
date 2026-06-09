# Uni Monitor Bot

Telegram-бот для мониторинга LP-позиций Uniswap v3 (Arbitrum) и Aerodrome (Base) с AI-анализом.

> Job Monitor Bot (поиск вакансий) вынесен в отдельный репозиторий `job-monitor-bot`.

## Функции

- 📊 `/status` — текущее состояние всех позиций
- 🧠 `/analyze` — AI-анализ с рекомендациями
- 🚨 Автоматические уведомления при выходе из диапазона

## Деплой на Railway

### 1. Переменные окружения

В Railway → твой проект → Variables добавь:

| Переменная | Значение |
|---|---|
| `TELEGRAM_TOKEN` | Токен от @BotFather |
| `ANTHROPIC_API_KEY` | sk-ant-... |
| `WALLET_ADDRESS` | 0x твой адрес |
| `CHAT_ID` | Твой Telegram chat_id |
| `CHECK_INTERVAL` | 600 (секунды, по умолчанию 10 мин) |

### 2. Как узнать свой CHAT_ID

Напиши боту @userinfobot в Telegram — он пришлёт твой id.

### 3. Деплой

1. Загрузи файлы в GitHub репозиторий
2. В Railway → New Project → Deploy from GitHub
3. Выбери репозиторий
4. Добавь переменные (шаг 1)
5. Deploy!

## Структура

```
bot.py          — основной файл бота
monitor.py      — получение позиций через Web3
ai_analyst.py   — AI анализ через Claude API
requirements.txt
Procfile        — для Railway
```
